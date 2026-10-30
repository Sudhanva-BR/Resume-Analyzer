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

def _extract_pdf_data(pdf_bytes: bytes) -> tuple[str, list[str], list[dict]]:
    """
    Extract visible text AND all embedded URI hyperlinks from the PDF,
    including the clipped text under each link's bounding box.
    Returns: (full_text, list_of_hyperlink_urls, list_of_detailed_links)
    """
    text = ""
    links = []
    detailed_links = []
    try:
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        for page in doc:
            text += page.get_text() + "\n"
            for link in page.get_links():
                uri = link.get("uri")
                rect = link.get("from")
                if uri:
                    links.append(uri)
                    clip_text = page.get_text("text", clip=rect).strip() if rect else ""
                    detailed_links.append({"uri": uri, "text": clip_text})
        doc.close()
    except Exception:
        pass
    return text, links, detailed_links


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


# ───────────────── ICPC achievement extraction ──────────────────

_ICPC_TEXT_PATTERNS = [
    # "ICPC regionalist in 2025", "ICPC regionalist 2026", "ACM-ICPC Regional Finalist 2024"
    re.compile(
        r"((?:ACM[- ]?)?ICPC\s+[A-Za-z0-9\-]*\s*(?:regional(?:ist)?|finalist|qualifier|participant|selected|qualified)"
        r"(?:\s+in)?\s*(?:20\d{2})?"
        r"[^.\n]{0,60}?(?:20\d{2})?)",
        re.I,
    ),
    # "Selected for ICPC Regionals 2025", "Qualified for ICPC Regionals"
    re.compile(
        r"((?:selected|qualified|participated)\s+(?:for|in)\s+(?:ACM[- ]?)?ICPC[^.\n]{0,80})",
        re.I,
    ),
    # "ICPC Asia West Regionals", "ICPC Amritapuri Regionals"
    re.compile(
        r"((?:ACM[- ]?)?ICPC\s+(?:Asia|Europe|Africa|Latin|North|South|World|Amritapuri|Kanpur|Gwalior|Chennai|Pune)[^.\n]{0,80})",
        re.I,
    ),
    # Broad catch: any line mentioning "ICPC" + a year
    re.compile(
        r"((?:ACM[- ]?)?ICPC[^.\n]{0,100}?20\d{2})",
        re.I,
    ),
]


def _clean_icpc_achievement(text: str) -> str:
    """Format and normalize an ICPC achievement string into a clean standard form."""
    clean = " ".join(text.split())
    clean = re.sub(r"^[•·\-\*\|\d\.\s\:\#\(\)]+", "", clean).strip()
    clean = clean.rstrip(".,;:|•–—()")

    year_match = re.search(r"\b(20\d{2})\b", clean)
    year = year_match.group(1) if year_match else None

    if re.search(r"\bicpc\b.*\bregionalist\b", clean, re.I):
        return f"ICPC regionalist in {year}" if year else "ICPC regionalist"
    elif re.search(r"\bicpc\b.*\bregional\s+finalist\b", clean, re.I):
        return f"ICPC regional finalist in {year}" if year else "ICPC regional finalist"
    elif re.search(r"\b(?:qualified|selected)\b.*\bicpc\s+regionals?\b", clean, re.I):
        return f"Qualified for ICPC Regionals in {year}" if year else "Qualified for ICPC Regionals"
    elif re.search(r"\bicpc\s+world\s+finals?\b", clean, re.I):
        return f"ICPC World Finalist in {year}" if year else "ICPC World Finalist"
    else:
        m = re.search(r"((?:ACM[- ]?)?ICPC\s+[^,\.\;\n]{4,50})", clean, re.I)
        if m:
            c = m.group(1).strip().rstrip(".,;:|•–—()")
            if year and year not in c:
                c += f" in {year}"
            return c
        return clean


def _extract_icpc_achievements(text: str, detailed_links: list[dict]) -> list[dict]:
    """
    Extract ICPC-related achievements from resume text.
    Returns a list of dicts: [{"text": "ICPC regionalist in 2025", "url": "..." or None}]
    """
    achievements = []
    seen = set()

    # Look for ICPC link in detailed_links first
    icpc_link = None
    for item in detailed_links:
        u = item.get("uri", "")
        t = item.get("text", "")
        if "icpc" in u.lower() or "icpc" in t.lower() or "regionalist" in t.lower():
            icpc_link = u
            break

    # 1. Scan line by line for precise context
    for line in text.splitlines():
        if not re.search(r"\bicpc\b", line, re.I):
            continue
        if not re.search(
            r"\b(regional(?:ist)?|finalist|qualifier|participant|selected|qualified|rank|finals?|asia|amritapuri|kanpur|gwalior|chennai|pune)\b",
            line,
            re.I,
        ):
            continue

        cleaned = _clean_icpc_achievement(line)
        norm = cleaned.lower()
        if norm and norm not in seen and len(cleaned) >= 8:
            seen.add(norm)
            achievements.append({
                "text": cleaned,
                "url": icpc_link,
            })

    # 2. Pattern fallback across the full text
    if not achievements:
        for pat in _ICPC_TEXT_PATTERNS:
            for m in pat.finditer(text):
                cleaned = _clean_icpc_achievement(m.group(1))
                norm = cleaned.lower()
                if norm and norm not in seen and len(cleaned) >= 8:
                    seen.add(norm)
                    achievements.append({
                        "text": cleaned,
                        "url": icpc_link,
                    })

    return achievements


# ───────────────── Portfolio link extraction ──────────────────

_PORTFOLIO_EXCLUDE = {
    "linkedin.com", "github.com", "codeforces.com", "codechef.com",
    "leetcode.com", "hackerrank.com", "hackerearth.com", "kaggle.com",
    "drive.google.com", "docs.google.com", "geeksforgeeks.org",
    "codingninjas.com", "interviewbit.com", "youtube.com",
    "medium.com", "twitter.com", "x.com", "facebook.com",
}

_PORTFOLIO_LABEL_PATTERN = re.compile(
    r"(?:portfolio|personal\s*(?:website|site|page))\s*[:\-–—|]?\s*(https?://[^\s<>\"')\]]+)",
    re.I,
)


def _extract_portfolio_links(text: str, detailed_links: list[dict]) -> list[str]:
    """
    Extract portfolio / personal website URL from resume.
    Returns list of at most 1 primary portfolio URL if found.
    """
    seen = set()
    found = []

    # 1. Check detailed links for explicit portfolio anchor text or uri
    for item in detailed_links:
        u = item.get("uri", "").strip().rstrip("/.,;:)")
        t = item.get("text", "").lower()
        if not u or not u.startswith("http"):
            continue
        domain = urllib.parse.urlparse(u).netloc.lower().lstrip("www.")
        if any(ex in domain for ex in _PORTFOLIO_EXCLUDE):
            continue

        # Explicit portfolio label in link text or URL
        if "portfolio" in t or "portfolio" in u.lower():
            if u.lower() not in seen:
                seen.add(u.lower())
                found.append(u)
                return found

    # 2. Check explicit labels in text, e.g. "Portfolio: https://..."
    for m in _PORTFOLIO_LABEL_PATTERN.finditer(text):
        u = m.group(1).strip().rstrip(".,;:)")
        domain = urllib.parse.urlparse(u).netloc.lower().lstrip("www.")
        if not any(ex in domain for ex in _PORTFOLIO_EXCLUDE):
            if u.lower() not in seen:
                seen.add(u.lower())
                found.append(u)
                return found

    # 3. Check for personal domain / github.io / vercel / netlify
    for item in detailed_links:
        u = item.get("uri", "").strip().rstrip("/.,;:)")
        t = item.get("text", "").lower()
        if not u or not u.startswith("http"):
            continue
        domain = urllib.parse.urlparse(u).netloc.lower().lstrip("www.")
        if any(ex in domain for ex in _PORTFOLIO_EXCLUDE):
            continue
        # Avoid demo apps (e.g. course-management, e-commerce, clone, dashboard, etc.)
        if any(demo in u.lower() for demo in ["demo", "app", "clone", "course", "shop", "stock", "weather", "chat"]):
            continue
        if any(h in domain for h in ["github.io", "vercel.app", "netlify.app", "pages.dev"]):
            if u.lower() not in seen:
                seen.add(u.lower())
                found.append(u)
                return found

    return found


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
            "icpc_achievements": list[dict],
            "portfolio_links": list[str],
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
        "icpc_achievements": [],
        "portfolio_links": [],
        "error": None,
    }

    pdf_bytes = _download_pdf_bytes(url)
    if pdf_bytes is None:
        result["error"] = "Failed to download PDF"
        return result

    text, hyperlinks, detailed_links = _extract_pdf_data(pdf_bytes)
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

    # ICPC achievements and portfolio links
    result["icpc_achievements"] = _extract_icpc_achievements(text, detailed_links)
    result["portfolio_links"] = _extract_portfolio_links(text, detailed_links)

    return result
