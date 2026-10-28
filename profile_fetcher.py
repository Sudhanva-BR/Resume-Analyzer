"""
profile_fetcher.py
──────────────────
Fetch competitive-programming stats from Codeforces, CodeChef, and LeetCode
using public APIs and web scraping.

Each platform fetcher returns:
    {
        "max_rating":      int | None,
        "contests_to_max": int | None,
        "penalised":       bool,          # True if caught cheating in a contest
        "penalty_details": str | None,   # Contest code/name where caught
        "error":           str | None,
    }
"""

import json
import re
import time
import requests
from bs4 import BeautifulSoup


_BROWSER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)

_SESSION = requests.Session()
_SESSION.headers.update({"User-Agent": _BROWSER_UA})


# ─────────────────────────────────────────────
#  Codeforces (Official API)
# ─────────────────────────────────────────────

def fetch_codeforces(handle: str) -> dict:
    """
    Fetch Codeforces user contest rating history and check for plagiarism/cheating penalties.
    """
    result = {
        "max_rating": None,
        "contests_to_max": None,
        "penalised": False,
        "penalty_details": None,
        "error": None,
    }
    handle = handle.strip()
    if not handle:
        result["error"] = "Empty handle"
        return result

    try:
        # 1. Rating history
        url = f"https://codeforces.com/api/user.rating?handle={handle}"
        resp = _SESSION.get(url, timeout=15)
        data = resp.json()

        if data.get("status") == "OK":
            history = data.get("result", [])
            if history:
                max_rating = -1
                contest_index_of_max = 0
                for idx, entry in enumerate(history):
                    new_rating = entry.get("newRating", 0)
                    if new_rating > max_rating:
                        max_rating = new_rating
                        contest_index_of_max = idx

                result["max_rating"] = max_rating
                result["contests_to_max"] = contest_index_of_max + 1
            else:
                u_url = f"https://codeforces.com/api/user.info?handles={handle}"
                u_resp = _SESSION.get(u_url, timeout=15).json()
                if u_resp.get("status") == "OK" and u_resp.get("result"):
                    info = u_resp["result"][0]
                    result["max_rating"] = info.get("maxRating")
                    result["contests_to_max"] = None
        else:
            result["error"] = data.get("comment", "Codeforces API error")

        # 2. Check for contest disqualification / plagiarism (SKIPPED in official contest)
        try:
            status_url = f"https://codeforces.com/api/user.status?handle={handle}&from=1&count=150"
            s_resp = _SESSION.get(status_url, timeout=10).json()
            if s_resp.get("status") == "OK":
                for sub in s_resp.get("result", []):
                    # Official contest participant solution disqualified
                    if (
                        sub.get("verdict") == "SKIPPED"
                        and sub.get("author", {}).get("participantType") == "CONTESTANT"
                    ):
                        cid = sub.get("contestId", "")
                        pname = sub.get("problem", {}).get("name", "")
                        result["penalised"] = True
                        result["penalty_details"] = f"Codeforces Contest {cid} ({pname})"
                        break
        except Exception:
            pass

    except Exception as exc:
        result["error"] = str(exc)

    return result


# ─────────────────────────────────────────────
#  CodeChef (Stats API + Web Scraping Fallback)
# ─────────────────────────────────────────────

def fetch_codechef(handle: str) -> dict:
    """
    Fetch CodeChef stats and check for MOSS plagiarism penalties.
    """
    result = {
        "max_rating": None,
        "contests_to_max": None,
        "penalised": False,
        "penalty_details": None,
        "error": None,
    }
    handle = handle.strip()
    if not handle:
        result["error"] = "Empty handle"
        return result

    # --- Method 1: CodeChef stats rating history endpoint ---
    try:
        api_url = f"https://codechef-stats.tashif.codes/rating/{handle}"
        resp = _SESSION.get(api_url, timeout=12)
        if resp.status_code == 200:
            data = resp.json()
            rating_data = data.get("ratingData", [])
            if rating_data:
                max_rating = -1
                idx_of_max = 0
                for idx, c in enumerate(rating_data):
                    # Check for official plagiarism penalty
                    if c.get("penalised") or c.get("reason") == "penalised":
                        result["penalised"] = True
                        result["penalty_details"] = f"CodeChef Contest {c.get('code', 'START')}"

                    try:
                        r = int(c.get("rating", 0))
                        if r > max_rating:
                            max_rating = r
                            idx_of_max = idx
                    except (ValueError, TypeError):
                        continue

                if max_rating > 0:
                    result["max_rating"] = max_rating
                    result["contests_to_max"] = idx_of_max + 1
                    return result
    except Exception:
        pass

    # --- Method 2: Scrape official CodeChef profile page ---
    try:
        profile_url = f"https://www.codechef.com/users/{handle}"
        resp2 = _SESSION.get(profile_url, timeout=15)
        if resp2.status_code == 404:
            result["error"] = "User not found"
            return result
        resp2.raise_for_status()

        html = resp2.text

        # Extract highest rating
        m_high = re.search(r"Highest\s+Rating\s*(\d+)", html, re.I)
        if m_high:
            result["max_rating"] = int(m_high.group(1))

        if result["max_rating"] is None:
            soup = BeautifulSoup(html, "html.parser")
            rating_div = soup.find("div", class_="rating-number")
            if rating_div:
                try:
                    result["max_rating"] = int(rating_div.text.strip())
                except ValueError:
                    pass

        m_cnt = re.search(r"Contests?\s+Participated:\s*(\d+)", html, re.I)
        if m_cnt:
            result["contests_to_max"] = int(m_cnt.group(1))

        # Check for embedded rating history json in scripts
        for s in re.finditer(r"allMatch\s*=\s*JSON\.parse\(\s*'([^']+)'\s*\)", html):
            try:
                raw = s.group(1).encode().decode("unicode-escape")
                arr = json.loads(raw)
                if arr:
                    max_r = -1
                    idx_max = 0
                    for idx, item in enumerate(arr):
                        if item.get("penalised") or item.get("reason") == "penalised":
                            result["penalised"] = True
                            result["penalty_details"] = f"CodeChef {item.get('name', 'Contest')}"

                        r = int(item.get("rating") or item.get("score") or 0)
                        if r > max_r:
                            max_r = r
                            idx_max = idx
                    if max_r > 0:
                        result["max_rating"] = max_r
                        result["contests_to_max"] = idx_max + 1
                        return result
            except Exception:
                pass

        if result["max_rating"] is None:
            result["error"] = "Could not parse CodeChef rating"

    except Exception as exc:
        result["error"] = str(exc)

    return result


# ─────────────────────────────────────────────
#  LeetCode (GraphQL API)
# ─────────────────────────────────────────────

_LC_GRAPHQL_URL = "https://leetcode.com/graphql"

_LC_QUERY = """
query userContestRankingHistory($username: String!) {
  userContestRanking(username: $username) {
    attendedContestsCount
    rating
    globalRanking
  }
  userContestRankingHistory(username: $username) {
    attended
    rating
    ranking
    contest {
      title
      startTime
    }
  }
}
"""


def fetch_leetcode(handle: str) -> dict:
    """
    Query LeetCode GraphQL endpoint for contest ranking and history.
    """
    result = {
        "max_rating": None,
        "contests_to_max": None,
        "penalised": False,
        "penalty_details": None,
        "error": None,
    }
    handle = handle.strip()
    if not handle:
        result["error"] = "Empty handle"
        return result

    try:
        headers = {
            "Content-Type": "application/json",
            "Referer": "https://leetcode.com",
            "User-Agent": _BROWSER_UA,
        }
        payload = {
            "query": _LC_QUERY,
            "variables": {"username": handle},
        }
        resp = requests.post(
            _LC_GRAPHQL_URL, json=payload, headers=headers, timeout=15
        )
        resp.raise_for_status()
        data = resp.json()

        errors = data.get("errors")
        if errors:
            result["error"] = errors[0].get("message", "GraphQL error")
            return result

        gql_data = data.get("data", {})
        ranking = gql_data.get("userContestRanking")
        history = gql_data.get("userContestRankingHistory")

        if not history and not ranking:
            result["error"] = "No contest participation"
            return result

        attended = [e for e in history if e.get("attended")] if history else []

        if attended:
            max_rating = -1.0
            idx_max = 0
            for idx, entry in enumerate(attended):
                r = entry.get("rating", 0)
                if r and r > max_rating:
                    max_rating = r
                    idx_max = idx

            if max_rating > 0:
                result["max_rating"] = round(max_rating)
                result["contests_to_max"] = idx_max + 1
                return result

        if ranking and ranking.get("rating"):
            result["max_rating"] = round(ranking["rating"])
            result["contests_to_max"] = ranking.get("attendedContestsCount")
        else:
            result["error"] = "No contest history"

    except Exception as exc:
        result["error"] = str(exc)

    return result


# ─────────────────────────────────────────────
#  Batch Fetcher with Cheating/Penalty Check
# ─────────────────────────────────────────────

def _fetch_best_profile(fetch_func, handles: list[str] | str | None) -> dict:
    """
    Try all candidate handles and pick the profile with the highest max rating.
    Also retains any detected penalty.
    """
    if not handles:
        return {
            "max_rating": None,
            "contests_to_max": None,
            "penalised": False,
            "penalty_details": None,
            "error": "No handle found",
        }

    if isinstance(handles, str):
        handles = [handles]

    best = {
        "max_rating": None,
        "contests_to_max": None,
        "penalised": False,
        "penalty_details": None,
        "error": None,
    }

    for h in handles:
        if not h:
            continue
        stats = fetch_func(h)
        # Keep penalty if detected on any handle
        if stats.get("penalised"):
            best["penalised"] = True
            best["penalty_details"] = stats.get("penalty_details")

        if stats.get("max_rating") is not None:
            if best["max_rating"] is None or stats["max_rating"] > best["max_rating"]:
                best["max_rating"] = stats["max_rating"]
                best["contests_to_max"] = stats["contests_to_max"]
        elif best["max_rating"] is None and stats.get("error"):
            best["error"] = stats["error"]
        time.sleep(0.3)

    return best


def fetch_all_profiles(
    codeforces: list[str] | str | None,
    codechef: list[str] | str | None,
    leetcode: list[str] | str | None,
) -> dict:
    """
    Fetch stats and check contest cheating penalties across all platforms.
    """
    cf_res = _fetch_best_profile(fetch_codeforces, codeforces)
    cc_res = _fetch_best_profile(fetch_codechef, codechef)
    lc_res = _fetch_best_profile(fetch_leetcode, leetcode)

    has_any = bool(codeforces or codechef or leetcode)

    caught_list = []
    if cf_res.get("penalised"):
        caught_list.append(cf_res.get("penalty_details") or "Codeforces")
    if cc_res.get("penalised"):
        caught_list.append(cc_res.get("penalty_details") or "CodeChef")
    if lc_res.get("penalised"):
        caught_list.append(lc_res.get("penalty_details") or "LeetCode")

    if not has_any:
        cheating_status = "NA"
    elif caught_list:
        cheating_status = "🚨 Caught (" + ", ".join(caught_list) + ")"
    else:
        cheating_status = "🟢 Clean"

    return {
        "codeforces": cf_res,
        "codechef": cc_res,
        "leetcode": lc_res,
        "cheating_status": cheating_status,
        "caught_penalties": caught_list,
    }
