"""
pdf_parser.py
─────────────
Download a resume PDF (Google Drive, CodeChef recruiter link, direct HTTP)
and extract:
  - Candidate name
  - Codeforces, CodeChef, and LeetCode usernames (from text AND embedded hyperlinks)
  - Inline ratings explicitly stated in resume text
"""

import io
import os
import re
import tempfile
import urllib.parse

import gdown
import fitz  # PyMuPDF
import requests


_BROWSER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)


def _is_google_drive_link(url: str) -> bool:
    """Check if a URL is a Google Drive link."""
    return "drive.google.com" in url or "docs.google.com" in url


def _download_pdf_bytes(url: str) -> bytes | None:
    """
    Download PDF from URL. Supports:
      - Google Drive share links (direct export + confirmation + gdown fallback)
      - CodeChef recruiter download links
      - Direct HTTP links
    """
    url = url.strip()
    if not url:
        return None

    # --- Method 1: Google Drive link handling ---
    if _is_google_drive_link(url):
        m = re.search(r"/d/([a-zA-Z0-9_-]+)", url) or re.search(r"id=([a-zA-Z0-9_-]+)", url)
        if m:
            fid = m.group(1)
            session = requests.Session()
            session.headers.update({"User-Agent": _BROWSER_UA})
            try:
                download_url = f"https://drive.google.com/uc?export=download&id={fid}"
                resp = session.get(download_url, timeout=20, allow_redirects=True)
                # Check for virus scan confirmation token if file is large
                if "confirm=" in resp.text:
                    token_m = re.search(r"confirm=([0-9A-Za-z_]+)", resp.text)
                    if token_m:
                        resp = session.get(
                            f"{download_url}&confirm={token_m.group(1)}",
                            timeout=20,
                            allow_redirects=True,
                        )
                if resp.status_code == 200 and len(resp.content) > 500:
                    if resp.content[:5] == b"%PDF-" or resp.headers.get("Content-Type", "").startswith("application/pdf"):
                        return resp.content
                    if b"%PDF-" in resp.content[:1024]:
                        return resp.content
            except Exception:
                pass

        # Fallback to gdown for Google Drive
        try:
            tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
            tmp.close()
            output_path = gdown.download(url, tmp.name, quiet=True, fuzzy=True)
            if output_path is not None and os.path.exists(output_path):
                with open(output_path, "rb") as f:
                    data = f.read()
                os.unlink(output_path)
                if len(data) > 500:
                    return data
        except Exception:
            pass

    # --- Method 2: Direct HTTP / CodeChef Recruiter download ---
    try:
        resp = requests.get(
            url,
            headers={"User-Agent": _BROWSER_UA},
            timeout=30,
            allow_redirects=True,
        )
        resp.raise_for_status()
        if len(resp.content) > 500:
            return resp.content
    except Exception:
        pass

    return None


# ───────────────── PDF content extraction ──────────────────

def _extract_pdf_data(pdf_bytes: bytes) -> tuple[str, list[str]]:
    """
    Extract visible text AND all embedded URI hyperlinks from the PDF.
    Returns: (full_text, list_of_hyperlink_urls)
    """
    text = ""
    links = []
    try:
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        for page in doc:
            text += page.get_text() + "\n"
            for link in page.get_links():
                uri = link.get("uri")
                if uri:
                    links.append(uri)
        doc.close()
    except Exception:
        pass
    return text, links


# ───────────────── Name extraction ──────────────────

def _extract_candidate_name(text: str) -> str:
    """
    Extract candidate name from top lines of the resume text.
    """
    lines = text.strip().splitlines()
    for line in lines[:15]:
        line = line.strip()
        if not line or len(line) < 3:
            continue
        if re.search(r"[0-9]{4,}", line):
            continue
        if "@" in line or "http" in line.lower() or "github" in line.lower() or "linkedin" in line.lower():
            continue
        clean_line = re.sub(r"[|•·\-–—ƒ#ï§Ð‡]", " ", line).strip()
        words = clean_line.split()
        if 1 <= len(words) <= 5 and all(w[0].isupper() or w[0] == "(" for w in words if w):
            if len(clean_line) >= 3 and not any(kw in clean_line.lower() for kw in ["resume", "curriculum", "page"]):
                return clean_line
    return "Unknown"


# ───────────────── Username extraction ──────────────────

_CF_PATTERNS = [
    re.compile(r"codeforces\.com/(?:profile|contests/with)/([A-Za-z0-9_.\-]+)", re.I),
    re.compile(r"[Cc]odeforces\s*\(handle[:\s]*([A-Za-z0-9_.\-]+)\)", re.I),
    re.compile(r"[Cc]odeforces\s*[:\-–—|]\s*([A-Za-z0-9_.\-]+)", re.I),
]

_CC_PATTERNS = [
    re.compile(r"codechef\.com/users/([A-Za-z0-9_]+)", re.I),
    re.compile(r"[Cc]odechef\s*\(handle[:\s]*([A-Za-z0-9_]+)\)", re.I),
    re.compile(r"[Cc]odechef\s*[:\-–—|]\s*([A-Za-z0-9_]+)", re.I),
]

_LC_PATTERNS = [
    re.compile(r"leetcode\.com/(?:u/)?([A-Za-z0-9_.\-]+)/?", re.I),
    re.compile(r"[Ll]eetcode\s*\(handle[:\s]*([A-Za-z0-9_.\-]+)\)", re.I),
    re.compile(r"[Ll]eetcode\s*[:\-–—|]\s*([A-Za-z0-9_.\-]+)", re.I),
]

_IGNORED_HANDLES = {
    "u", "user", "users", "profile", "contests", "contest", "problem",
    "problems", "ranking", "rankings", "leaderboard", "discuss", "explore"
}


def _find_all_usernames(combined_text: str, patterns: list[re.Pattern]) -> list[str]:
    """
    Find all candidate handles matching patterns from text and hyperlinks.
    Preserves discovery order while deduplicating.
    """
    found = []
    seen = set()
    for pat in patterns:
        for m in pat.finditer(combined_text):
            h = m.group(1).strip().rstrip("/.,;:()")
            if h and len(h) >= 2 and h.lower() not in _IGNORED_HANDLES:
                if h.lower() not in seen:
                    seen.add(h.lower())
                    found.append(h)
    return found


# ───────────────── Inline text rating extraction ──────────────────

def _extract_rating_from_text(text: str, platform: str) -> int | None:
    """
    Search resume text for ratings mentioned in achievement sections.
    Handles:
      - 'LeetCode ... peak contest rating of 2,022'
      - 'LeetCode ... 1990+ Rating'
      - 'CodeChef: 3 Star | 1700+ Rating'
      - 'Specialist rank (1500 rating) on Codeforces'
    """
    flat = " ".join(text.splitlines())

    # 1. 'platform ... rating[:/]? N,NNN+' or 'platform ... peak contest rating of N,NNN+'
    p1 = re.search(
        rf"{platform}[^.•\n]{{0,120}}?(?:peak\s+|max\s+|highest\s+|contest\s+)?(?:rating|rated)\s*(?:of|is|:|-)?\s*(\d{{1,2}},?\d{{3}}|\d{{3,4}})\+?",
        flat,
        re.I,
    )
    if p1:
        return int(p1.group(1).replace(",", ""))

    # 2. 'platform ... N,NNN+ Rating'
    p2 = re.search(
        rf"{platform}[^.•\n]{{0,120}}?(\d{{1,2}},?\d{{3}}|\d{{3,4}})\+?\s*(?:rating|rated)",
        flat,
        re.I,
    )
    if p2:
        return int(p2.group(1).replace(",", ""))

    # 3. '(N,NNN rating) on platform' or '(N,NNN) rating on platform'
    p3 = re.search(
        r"\((\d{1,2},?\d{3}|\d{3,4})\+?\s*(?:rating)?\)\s*(?:rating\s+)?(?:on\s+)?" + re.escape(platform),
        flat,
        re.I,
    )
    if p3:
        return int(p3.group(1).replace(",", ""))

    # 4. 'N,NNN rating ... on platform'
    p4 = re.search(
        r"(\d{1,2},?\d{3}|\d{3,4})\+?\s*(?:rating|rated)[^.•\n]{0,60}?" + re.escape(platform),
        flat,
        re.I,
    )
    if p4:
        return int(p4.group(1).replace(",", ""))

    return None


# ───────────────── Public parser entrypoint ──────────────────

def parse_resume(url: str) -> dict:
    """
    Parse a resume from URL.
    Returns:
        {
            "url": str,
            "name": str,
            "codeforces": str | None,
            "codechef": str | None,
            "leetcode": str | None,
            "cf_handles": list[str],
            "cc_handles": list[str],
            "lc_handles": list[str],
            "cf_text_rating": int | None,
            "cc_text_rating": int | None,
            "lc_text_rating": int | None,
            "error": str | None,
        }
    """
    result = {
        "url": url,
        "name": "Unknown",
        "codeforces": None,
        "codechef": None,
        "leetcode": None,
        "cf_handles": [],
        "cc_handles": [],
        "lc_handles": [],
        "cf_text_rating": None,
        "cc_text_rating": None,
        "lc_text_rating": None,
        "error": None,
    }

    pdf_bytes = _download_pdf_bytes(url)
    if pdf_bytes is None:
        result["error"] = "Failed to download PDF"
        return result

    text, hyperlinks = _extract_pdf_data(pdf_bytes)
    if not text.strip() and not hyperlinks:
        result["error"] = "Could not extract text or links from PDF"
        return result

    combined_corpus = text + "\n" + "\n".join(hyperlinks)

    result["name"] = _extract_candidate_name(text)

    # Collect all matching handles for each platform
    cf_list = _find_all_usernames(combined_corpus, _CF_PATTERNS)
    cc_list = _find_all_usernames(combined_corpus, _CC_PATTERNS)
    lc_list = _find_all_usernames(combined_corpus, _LC_PATTERNS)

    result["cf_handles"] = cf_list
    result["cc_handles"] = cc_list
    result["lc_handles"] = lc_list

    result["codeforces"] = cf_list[0] if cf_list else None
    result["codechef"] = cc_list[0] if cc_list else None
    result["leetcode"] = lc_list[0] if lc_list else None

    # Fallback ratings from text
    result["cf_text_rating"] = _extract_rating_from_text(text, "Codeforces")
    result["cc_text_rating"] = _extract_rating_from_text(text, "Codechef") or _extract_rating_from_text(text, "CodeChef")
    result["lc_text_rating"] = _extract_rating_from_text(text, "Leetcode") or _extract_rating_from_text(text, "LeetCode")

    return result
