"""
app.py  –  Resume Competitive-Programming Profile Analyzer
──────────────────────────────────────────────────────────
A Streamlit dashboard that:
  1. Accepts resume PDF links (Google Drive, CodeChef recruiter, direct HTTP).
  2. Extracts candidate names & CP handles from text + embedded hyperlinks.
  3. Fetches max rating & contest count for Codeforces, CodeChef, and LeetCode.
  4. Detects if the candidate was caught/penalized for contest cheating/plagiarism.
  5. Displays numbered cards, full data table with Cheating Status, and metrics.
  6. Provides Excel & CSV downloads with session-only memory.
"""

import importlib
import io
import re
import time

import pandas as pd
import streamlit as st

import pdf_parser
import profile_fetcher

# Ensure fresh module reloads
importlib.reload(pdf_parser)
importlib.reload(profile_fetcher)

from pdf_parser import parse_resume
from profile_fetcher import fetch_all_profiles

# ──────────────── Page config ────────────────

st.set_page_config(
    page_title="CP Profile Analyzer",
    page_icon="🏆",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ──────────────── Custom CSS ────────────────

st.markdown(
    """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');

    html, body, [class*="css"] {
        font-family: 'Inter', sans-serif;
    }

    .hero-title {
        text-align: center;
        padding: 1.2rem 0 0.2rem;
        font-size: 2.4rem;
        font-weight: 800;
        background: linear-gradient(135deg, #6C63FF, #3B82F6, #06B6D4);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        letter-spacing: -0.5px;
    }
    .hero-sub {
        text-align: center;
        color: #94a3b8;
        font-size: 1.05rem;
        margin-bottom: 1.6rem;
    }

    .metric-grid {
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(170px, 1fr));
        gap: 1rem;
        margin-bottom: 1.5rem;
    }
    .metric-card {
        background: linear-gradient(135deg, #1e293b 0%, #0f172a 100%);
        border: 1px solid #334155;
        border-radius: 16px;
        padding: 1.2rem 1.4rem;
        text-align: center;
        transition: transform 0.2s, box-shadow 0.2s;
    }
    .metric-card:hover {
        transform: translateY(-4px);
        box-shadow: 0 12px 28px rgba(99,102,241,0.15);
    }
    .metric-value {
        font-size: 2rem;
        font-weight: 700;
        background: linear-gradient(135deg, #818cf8, #38bdf8);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
    }
    .metric-value-alert {
        font-size: 2rem;
        font-weight: 700;
        color: #f87171 !important;
    }
    .metric-value-clean {
        font-size: 2rem;
        font-weight: 700;
        color: #34d399 !important;
    }
    .metric-label {
        font-size: 0.85rem;
        color: #94a3b8;
        margin-top: 0.3rem;
    }

    .candidate-card {
        background: linear-gradient(135deg, #1e293b 0%, #0f172a 100%);
        border: 1px solid #334155;
        border-radius: 16px;
        padding: 1.4rem 1.8rem;
        margin-bottom: 1.2rem;
        transition: transform 0.2s, box-shadow 0.2s;
    }
    .candidate-card:hover {
        transform: translateY(-3px);
        box-shadow: 0 10px 24px rgba(99,102,241,0.12);
    }
    .card-header-row {
        display: flex;
        justify-content: space-between;
        align-items: center;
        margin-bottom: 0.75rem;
    }
    .candidate-name {
        font-size: 1.25rem;
        font-weight: 700;
        color: #f8fafc;
    }
    .resume-idx-badge {
        background: #334155;
        color: #94a3b8;
        font-size: 0.78rem;
        font-weight: 600;
        padding: 0.25rem 0.6rem;
        border-radius: 6px;
    }
    .candidate-summary {
        font-size: 0.95rem;
        color: #cbd5e1;
        margin-bottom: 0.85rem;
        font-weight: 500;
        background: rgba(15, 23, 42, 0.6);
        padding: 0.6rem 1rem;
        border-radius: 8px;
        border-left: 4px solid #6366f1;
    }
    .platform-badges {
        display: flex;
        flex-wrap: wrap;
        gap: 0.7rem;
    }
    .badge {
        display: inline-flex;
        align-items: center;
        gap: 0.4rem;
        padding: 0.45rem 1rem;
        border-radius: 10px;
        font-size: 0.82rem;
        font-weight: 600;
        color: #f1f5f9;
    }
    .badge-cf  { background: linear-gradient(135deg, #4f46e5, #6366f1); }
    .badge-cc  { background: linear-gradient(135deg, #7c3aed, #8b5cf6); }
    .badge-lc  { background: linear-gradient(135deg, #d97706, #f59e0b); }
    .badge-clean { background: linear-gradient(135deg, #059669, #10b981); color: #fff; }
    .badge-caught { background: linear-gradient(135deg, #b91c1c, #ef4444); color: #fff; font-weight: 700; }
    .badge-na  { background: #334155; color: #94a3b8; }

    .stDownloadButton > button {
        border-radius: 10px !important;
        font-weight: 600 !important;
        padding: 0.5rem 1.5rem !important;
    }
    .section-divider {
        height: 2px;
        background: linear-gradient(90deg, transparent, #334155, transparent);
        margin: 1.5rem 0;
        border: none;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


# ──────────────── Helper functions ────────────────

def _val(v) -> str:
    """Format a value for display – show 'NA' for None."""
    return str(v) if v is not None else "NA"


def _best_rating(api_rating, text_rating):
    """
    Pick the most accurate available rating:
    - Prefer API data.
    - Fall back to text-extracted rating.
    """
    if api_rating is not None:
        return api_rating
    if text_rating is not None:
        return text_rating
    return None


def _merge_stats(parsed: dict, profiles: dict) -> dict:
    """
    Merge API-fetched stats with text-extracted fallback ratings and cheating status.
    """
    result = {**parsed}

    for platform, key_prefix in [
        ("codeforces", "cf"),
        ("codechef", "cc"),
        ("leetcode", "lc"),
    ]:
        api_stats = profiles[platform]
        text_rating = parsed.get(f"{key_prefix}_text_rating")

        final_rating = _best_rating(api_stats.get("max_rating"), text_rating)
        final_contests = api_stats.get("contests_to_max")
        total_contests = api_stats.get("total_contests")

        result[f"{key_prefix}_stats"] = {
            "max_rating": final_rating,
            "contests_to_max": final_contests,
            "total_contests": total_contests,
            "penalised": api_stats.get("penalised", False),
            "penalty_details": api_stats.get("penalty_details"),
            "error": api_stats.get("error"),
        }

    result["cheating_status"] = profiles.get("cheating_status", "NA")
    result["caught_penalties"] = profiles.get("caught_penalties", [])

    return result


def _platform_profile_url(platform: str, handle: str | None) -> str | None:
    """Return the profile URL for a given platform and handle, or None if no handle."""
    if not handle:
        return None
    if platform == "codeforces":
        return f"https://codeforces.com/profile/{handle}"
    if platform == "codechef":
        return f"https://www.codechef.com/users/{handle}"
    if platform == "leetcode":
        return f"https://leetcode.com/u/{handle}/"
    return None


def _parse_teaching_duration_to_months(duration_text: str | None) -> int | None:
    """Parse a duration string like '1 year', '6 months', '2+ years' into total months."""
    if not duration_text:
        return None
    text = duration_text.lower().strip()
    total_months = 0
    y_m = re.search(r"(\d+)\+?\s*(?:years?|yrs?)", text)
    if y_m:
        total_months += int(y_m.group(1)) * 12
    m_m = re.search(r"(\d+)\+?\s*(?:months?|mos?)", text)
    if m_m:
        total_months += int(m_m.group(1))
    return total_months if total_months > 0 else None


def _detect_candidate_level(result: dict) -> str:
    """
    Determine whether candidate is L3, L2, or L1 based on their ratings and experience:
    - L3: CF 1800+ or CC 2200+ or LC 2400+ and >= 6 months experience
    - L2: CF 1600+ or CC 2000+ or LC 2200+ and >= 6 months experience
    - L1: CF 1400+ or CC 1600+ or LC 1850+ and without exp or < 6 months experience
    """
    cf_rating = (result.get("cf_stats") or {}).get("max_rating")
    cc_rating = (result.get("cc_stats") or {}).get("max_rating")
    lc_rating = (result.get("lc_stats") or {}).get("max_rating")

    teaching = result.get("teaching_experience") or {}
    has_teaching = teaching.get("has_experience", False)
    duration_text = teaching.get("duration_text")
    months = _parse_teaching_duration_to_months(duration_text)

    has_at_least_6m = False
    if has_teaching:
        if months is not None:
            has_at_least_6m = (months >= 6)
        else:
            has_at_least_6m = True

    # 1. Check L3: CF 1800+ or CC 2200+ or LC 2400+ and >= 6 months experience
    l3_rating = (
        (cf_rating is not None and cf_rating >= 1800) or
        (cc_rating is not None and cc_rating >= 2200) or
        (lc_rating is not None and lc_rating >= 2400)
    )
    if l3_rating and has_at_least_6m:
        return "L3"

    # 2. Check L2: CF 1600+ or CC 2000+ or LC 2200+ and >= 6 months experience
    l2_rating = (
        (cf_rating is not None and cf_rating >= 1600) or
        (cc_rating is not None and cc_rating >= 2000) or
        (lc_rating is not None and lc_rating >= 2200)
    )
    if l2_rating and has_at_least_6m:
        return "L2"

    # 3. Default to L1
    return "L1"


def _compute_priority_and_fitment(result: dict, level: str) -> dict:
    """
    Compute Resume Shortlisting Priority (P1/P2/P3) and Candidate Fitment Score (0-5)
    based on the selected role level (or Auto-detected L1/L2/L3).
    """
    effective_level = _detect_candidate_level(result) if level == "Auto (Detect Level)" else level

    THRESHOLDS = {
        "L1": {
            "cf": 1400, "cc": 1600, "lc": 1850,
            "min_exp_months": 0, "contest_p3_all": 5, "contest_p1_given": 20,
        },
        "L2": {
            "cf": 1600, "cc": 2000, "lc": 2200,
            "min_exp_months": 6, "contest_p3_all": 10, "contest_p1_given": 30,
        },
        "L3": {
            "cf": 1800, "cc": 2200, "lc": 2400,
            "min_exp_months": 6, "contest_p3_all": 5, "contest_p1_given": 40,
        },
    }
    t = THRESHOLDS.get(effective_level, THRESHOLDS["L1"])

    # 1. Criteria 1: Rating threshold
    cf_rating = (result.get("cf_stats") or {}).get("max_rating")
    cc_rating = (result.get("cc_stats") or {}).get("max_rating")
    lc_rating = (result.get("lc_stats") or {}).get("max_rating")

    cf_met = cf_rating is not None and cf_rating >= t["cf"]
    cc_met = cc_rating is not None and cc_rating >= t["cc"]
    lc_met = lc_rating is not None and (
        lc_rating >= t["lc"] or (effective_level == "L3" and lc_rating >= 1850 and (cf_met or cc_met))
    )

    criteria1_met = cf_met or cc_met or lc_met

    # 2. Criteria 2: Teaching experience
    teaching = result.get("teaching_experience") or {}
    has_teaching = teaching.get("has_experience", False)
    duration_text = teaching.get("duration_text")
    months = _parse_teaching_duration_to_months(duration_text)

    criteria2_met = False
    if effective_level == "L1":
        # For L1: "no need of experience only rating is enough"
        criteria2_met = True
    else:
        # L2 / L3: at least 6 months experience
        if has_teaching:
            if months is not None:
                criteria2_met = (months >= t["min_exp_months"])
            else:
                criteria2_met = True

    # 3. Fitment Score calculation
    if effective_level == "L1":
        # "for L1, keep base as 3, if he have icpc +1, if his rating is very high +1"
        has_icpc = bool(result.get("icpc_achievements"))
        very_high = (
            (cf_rating is not None and cf_rating >= 1600) or
            (cc_rating is not None and cc_rating >= 1800) or
            (lc_rating is not None and lc_rating >= 2000)
        )
        if criteria1_met:
            fitment = 3
            if has_icpc:
                fitment += 1
            if very_high:
                fitment += 1
            fitment = min(5, fitment)
        else:
            fitment = 2
            if has_icpc:
                fitment += 1
    else:
        fitment = 5
        if not criteria1_met:
            fitment -= 1
        if not criteria2_met:
            fitment -= 1

    # 4. Priority calculation
    caught_count = len(result.get("caught_penalties", []))

    # Contest counts across all platforms where candidate participated
    active_contests_to_max = []
    given_contest_counts = []
    for prefix in ["cf", "cc", "lc"]:
        st = result.get(f"{prefix}_stats") or {}
        r = st.get("max_rating")
        c = st.get("contests_to_max")
        tot = st.get("total_contests")
        if r is not None and c is not None:
            active_contests_to_max.append(c)
        if tot is not None:
            given_contest_counts.append(tot)
        elif c is not None:
            given_contest_counts.append(c)

    priority = "P2"

    # P3 rule:
    # "if he is caught in more than one question of(reached max rating in less than X contest in codeforces and codechef and leetcode all) than P3"
    if caught_count > 1:
        priority = "P3"
    elif active_contests_to_max and all(c < t["contest_p3_all"] for c in active_contests_to_max):
        priority = "P3"
    elif effective_level == "L1":
        # For L1: only rating is enough, if given > 20 contests and criteria 1 met -> P1
        has_given_enough = given_contest_counts and (max(given_contest_counts) > t["contest_p1_given"] or sum(given_contest_counts) > t["contest_p1_given"])
        if criteria1_met and has_given_enough:
            priority = "P1"
        else:
            priority = "P2"
    else:
        # For L2/L3: needs experience and given enough contests -> P1
        has_given_enough = given_contest_counts and (max(given_contest_counts) > t["contest_p1_given"] or sum(given_contest_counts) > t["contest_p1_given"])
        if criteria1_met and criteria2_met and has_given_enough:
            priority = "P1"
        else:
            priority = "P2"

    return {
        "priority": priority,
        "level": effective_level,
        "fitment_score": max(0, fitment),
    }


def _build_results_df(results: list[dict]) -> pd.DataFrame:
    """Convert analysis results into a clean display DataFrame."""
    rows = []
    for idx, r in enumerate(results, 1):
        cf_handle = (r.get("cf_handles") or [None])[0] or r.get("codeforces")
        cc_handle = (r.get("cc_handles") or [None])[0] or r.get("codechef")
        lc_handle = (r.get("lc_handles") or [None])[0] or r.get("leetcode")

        icpc_list = r.get("icpc_achievements", [])
        icpc_display = ", ".join(i["text"] for i in icpc_list) if icpc_list else "NA"

        port_list = r.get("portfolio_links", [])
        port_display = port_list[0] if port_list else "NA"

        teaching = r.get("teaching_experience") or {}
        teach_display = (
            f"Yes ({teaching.get('duration_text')})"
            if teaching.get("duration_text")
            else ("Yes" if teaching.get("has_experience") else "No")
        )

        def _stats_disp(s):
            m = _val(s.get("max_rating"))
            c = _val(s.get("contests_to_max"))
            t = _val(s.get("total_contests"))
            if m == "NA":
                return "NA"
            return f"{m} in {c} contests (total: {t})"

        rows.append(
            {
                "#": idx,
                "Name": r["name"],
                "Priority": r.get("priority", "NA"),
                "Level": r.get("level", "NA"),
                "Fitment Score": r.get("fitment_score", "NA"),
                "Teaching Exp": teach_display,
                "Resume Link": r.get("url", ""),
                "ICPC / Achievements": icpc_display,
                "Portfolio": port_display,
                "Codeforces": _stats_disp(r.get("cf_stats", {})),
                "CodeChef": _stats_disp(r.get("cc_stats", {})),
                "LeetCode": _stats_disp(r.get("lc_stats", {})),
                "Contest Penalty / Caught": r.get("cheating_status") or "NA",
            }
        )
    return pd.DataFrame(rows)


def _to_excel(results: list[dict]) -> bytes:
    """
    Build Excel matching the exact format shown in the reference image:
    Columns: Name | Resume link | context | Resume Shortlisting Priority (P1 > P2 > P3) | Priority for (L1, L2, L3) | Candidate Fitment Score (out of 5) 0 - Poor , 5 - Good
    - Name, Resume link, Priority, Priority for, and Fitment Score are vertically merged across all sub-rows for each candidate.
    - Column 3 (context) has separate sub-rows with horizontal grid lines:
        1. ICPC achievement (if present, e.g. 'ICPC regionalist in 2025')
        2. Portfolio link (if present, 'check portfolio' with url below)
        3. Codeforces: Line 1 = 'Codeforces : {rating} in {c} contest and attempted {t} contest in total', Line 2 = profile URL (blue, underlined)
        4. CodeChef: Line 1 = 'CodeChef : {rating} in {c} contest and attempted {t} contest in total', Line 2 = profile URL (blue, underlined)
        5. Teaching experience: 'Have teaching experience of {dur}' or 'Have experience in teaching'
        6. LeetCode: Line 1 = 'LeetCode : {rating} in {c} contest and attempted {t} contest in total', Line 2 = profile URL (blue, underlined)
    - If a platform is not present, shows '{Platform} : NA' without a second URL line.
    """
    import openpyxl
    from openpyxl.styles import Alignment, Font, PatternFill, Border, Side
    from openpyxl.cell.rich_text import CellRichText, TextBlock
    from openpyxl.cell.text import InlineFont

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "CP Profiles"

    # ── Styles ──────────────────────────────────────────────
    header_fill = PatternFill("solid", fgColor="D9D9D9")
    thin   = Side(style="thin",   color="D3D3D3")
    medium = Side(style="medium", color="7F7F7F")

    link_font   = Font(color="0563C1", underline="single", name="Calibri", size=11)
    normal_font = Font(color="000000", name="Calibri", size=11)
    bold_font   = Font(bold=True, name="Calibri", size=11)

    inline_black = InlineFont(rFont="Calibri", sz=11, color="000000")
    inline_blue  = InlineFont(rFont="Calibri", sz=11, color="0563C1", u="single")

    left_bottom   = Alignment(horizontal="left",   vertical="bottom", wrap_text=True)
    right_bottom  = Alignment(horizontal="right",  vertical="bottom", wrap_text=True)
    center_bottom = Alignment(horizontal="center", vertical="bottom", wrap_text=True)
    mid_left      = Alignment(horizontal="left",   vertical="center", wrap_text=True)
    center_wrap   = Alignment(horizontal="center", vertical="center", wrap_text=True)
    left_wrap     = Alignment(horizontal="left",   vertical="center", wrap_text=True)

    # ── Headers ─────────────────────────────────────────────
    headers = [
        ("Name", center_wrap),
        ("Resume link", center_wrap),
        ("context", center_wrap),
        ("Resume\nShortlisting\nPriority\n(P1 > P2 > P3)", left_wrap),
        ("Priority for\n(L1, L2, L3)", left_wrap),
        ("Candidate Fitment Score\n(out of 5)\n0 - Poor , 5 - Good", left_wrap),
    ]

    for col_idx, (h, align) in enumerate(headers, 1):
        cell = ws.cell(row=1, column=col_idx, value=h)
        cell.font = bold_font
        cell.fill = header_fill
        cell.border = Border(
            left=medium if col_idx == 1 else thin,
            right=medium if col_idx == len(headers) else thin,
            top=medium,
            bottom=medium,
        )
        cell.alignment = align
    ws.row_dimensions[1].height = 65

    # ── Data rows ───────────────────────────────────────────
    current_row = 2
    for r in results:
        cf_handle = (r.get("cf_handles") or [None])[0] or r.get("codeforces")
        cc_handle = (r.get("cc_handles") or [None])[0] or r.get("codechef")
        lc_handle = (r.get("lc_handles") or [None])[0] or r.get("leetcode")

        handles = {
            "codeforces": cf_handle,
            "codechef":   cc_handle,
            "leetcode":   lc_handle,
        }
        stats_map = {
            "codeforces": r.get("cf_stats", {}),
            "codechef":   r.get("cc_stats", {}),
            "leetcode":   r.get("lc_stats", {}),
        }

        # Build sub-row items for Column C (context)
        sub_items = []

        # 1. ICPC achievements
        for icpc in r.get("icpc_achievements", []):
            sub_items.append({
                "text": icpc["text"],
                "url": icpc.get("url"),
            })

        # 2. Portfolio links
        for port_url in r.get("portfolio_links", []):
            sub_items.append({
                "text": "check portfolio",
                "url": port_url,
            })

        # Helper for platform item
        def _make_platform_item(key, label):
            h = handles[key]
            st = stats_map[key]
            prof_url = _platform_profile_url(key, h)
            r_val = st.get("max_rating")
            c_val = st.get("contests_to_max")
            t_val = st.get("total_contests")

            if r_val is not None:
                c_str = f"{c_val} contest" if c_val is not None else "NA contest"
                if t_val is not None:
                    text = f"{label} : {r_val} in {c_str} and attempted {t_val} contest in total"
                else:
                    text = f"{label} : {r_val} in {c_str}"
                return {"text": text, "url": prof_url}
            else:
                return {"text": f"{label} : NA", "url": None}

        # 3. Codeforces
        sub_items.append(_make_platform_item("codeforces", "Codeforces"))

        # 4. CodeChef
        sub_items.append(_make_platform_item("codechef", "CodeChef"))

        # 5. Teaching experience (if candidate has teaching experience)
        teaching = r.get("teaching_experience") or {}
        if teaching.get("has_experience"):
            dur = teaching.get("duration_text")
            if dur:
                sub_items.append({"text": f"Have teaching experience of {dur}", "url": None})
            else:
                sub_items.append({"text": "Have experience in teaching", "url": None})

        # 6. LeetCode
        sub_items.append(_make_platform_item("leetcode", "LeetCode"))

        n_sub = len(sub_items)
        start_row = current_row
        end_row = current_row + n_sub - 1

        # ── Merged columns: A (1), B (2), D (4), E (5), F (6) ────────
        if n_sub > 1:
            ws.merge_cells(start_row=start_row, start_column=1, end_row=end_row, end_column=1)
            ws.merge_cells(start_row=start_row, start_column=2, end_row=end_row, end_column=2)
            ws.merge_cells(start_row=start_row, start_column=4, end_row=end_row, end_column=4)
            ws.merge_cells(start_row=start_row, start_column=5, end_row=end_row, end_column=5)
            ws.merge_cells(start_row=start_row, start_column=6, end_row=end_row, end_column=6)

        # ── Write and style all sub-rows ─────────────────────
        for sub_idx, item in enumerate(sub_items):
            row_num = start_row + sub_idx
            is_top = (sub_idx == 0)
            is_bottom = (sub_idx == n_sub - 1)
            t_side = medium if is_top else thin
            b_side = medium if is_bottom else thin

            # Col A: Name
            cell_a = ws.cell(row=row_num, column=1)
            cell_a.border = Border(left=medium, right=thin, top=t_side, bottom=b_side)
            if is_top:
                cell_a.value = r["name"]
                cell_a.font = normal_font
                cell_a.alignment = left_bottom

            # Col B: Resume link
            cell_b = ws.cell(row=row_num, column=2)
            cell_b.border = Border(left=thin, right=thin, top=t_side, bottom=b_side)
            if is_top:
                resume_url = r.get("url", "")
                cell_b.value = resume_url
                if resume_url:
                    cell_b.hyperlink = resume_url
                    cell_b.font = link_font
                else:
                    cell_b.font = normal_font
                cell_b.alignment = left_bottom

            # Col C: Sub-row item
            cell_c = ws.cell(row=row_num, column=3)
            cell_c.border = Border(left=thin, right=thin, top=t_side, bottom=b_side)
            cell_c.alignment = mid_left

            if item.get("url"):
                # 2 lines: Line 1 text (black) + Line 2 URL (blue, underlined)
                rt = CellRichText(
                    TextBlock(inline_black, item["text"] + "\n"),
                    TextBlock(inline_blue, item["url"])
                )
                cell_c.value = rt
                cell_c.hyperlink = item["url"]
                ws.row_dimensions[row_num].height = 40
            else:
                # 1 line: plain text (e.g. 'ICPC regionalist in 2023', 'Have teaching experience of 1 year', or 'Codeforces : NA')
                cell_c.value = item["text"]
                cell_c.font = normal_font
                ws.row_dimensions[row_num].height = 20

            # Col D: Resume Shortlisting Priority
            cell_d = ws.cell(row=row_num, column=4)
            cell_d.border = Border(left=thin, right=thin, top=t_side, bottom=b_side)
            if is_top:
                cell_d.value = r.get("priority", "")
                cell_d.font = normal_font
                cell_d.alignment = left_bottom

            # Col E: Priority for (L1, L2, L3)
            cell_e = ws.cell(row=row_num, column=5)
            cell_e.border = Border(left=thin, right=thin, top=t_side, bottom=b_side)
            if is_top:
                cell_e.value = r.get("level", "")
                cell_e.font = normal_font
                cell_e.alignment = left_bottom

            # Col F: Candidate Fitment Score
            cell_f = ws.cell(row=row_num, column=6)
            cell_f.border = Border(left=thin, right=medium, top=t_side, bottom=b_side)
            if is_top:
                cell_f.value = r.get("fitment_score", "")
                cell_f.font = normal_font
                cell_f.alignment = right_bottom

        current_row += n_sub

    # ── Column widths ────────────────────────────────────────
    ws.column_dimensions["A"].width = 24
    ws.column_dimensions["B"].width = 55
    ws.column_dimensions["C"].width = 68
    ws.column_dimensions["D"].width = 18
    ws.column_dimensions["E"].width = 16
    ws.column_dimensions["F"].width = 24

    buffer = io.BytesIO()
    wb.save(buffer)
    return buffer.getvalue()


def _reset_app():
    """Reset input field and cleared cached analysis results."""
    st.session_state["urls_input"] = ""
    st.session_state.pop("results", None)


# ──────────────── UI ────────────────

st.markdown('<h1 class="hero-title">🏆 CP Profile Analyzer</h1>', unsafe_allow_html=True)
st.markdown(
    '<p class="hero-sub">Extract competitive-programming stats & contest integrity from resume PDFs — '
    "Codeforces · CodeChef · LeetCode</p>",
    unsafe_allow_html=True,
)

# --- Input section ---
with st.container():
    st.markdown("#### 📎 Paste Resume PDF Links")
    urls_text = st.text_area(
        "One URL per line (Google Drive share-links, CodeChef recruiter downloads, or direct PDF links)",
        height=160,
        placeholder=(
            "https://jobboard.codechef.com/api/recruiter/download?jobId=37&userId=54679&fieldId=235&token=...\n"
            "https://drive.google.com/file/d/1AbCdEfGh.../view?usp=sharing\n"
            "https://example.com/resume.pdf"
        ),
        key="urls_input",
    )

    col_level, col_info = st.columns([1.5, 3])
    with col_level:
        selected_level = st.selectbox(
            "🎯 Select Shortlisting Level",
            options=["Auto (Detect Level)", "L1", "L2", "L3"],
            index=0,
            key="selected_level",
            help=(
                "Auto: Automatically determines L1, L2, or L3 for each candidate\n"
                "L1: CF 1400+ / CC 1600+ / LC 1850+ (no exp needed) · Base fitment: 3 (+1 ICPC, +1 high rating)\n"
                "L2: CF 1600+ / CC 2000+ / LC 2200+ & ≥6 mos exp\n"
                "L3: CF 1800+ / CC 2200+ / LC 2400+ & ≥6 mos exp"
            ),
        )
    with col_info:
        st.markdown(
            """
            <div style="font-size:0.82rem; color:#94a3b8; margin-top:1.4rem; line-height:1.4;">
                <b>Auto:</b> Detects L1, L2, or L3 automatically per candidate<br>
                <b>L1:</b> CF 1400+ / CC 1600+ / LC 1850+ (no exp needed) · Base fitment: 3 (+1 ICPC, +1 high rating) · P1: &gt;20 contests<br>
                <b>L2:</b> CF 1600+ / CC 2000+ / LC 2200+ (≥6 mos exp) · P1: &gt;30 contests + exp · P3: all &lt;10 contests<br>
                <b>L3:</b> CF 1800+ / CC 2200+ / LC 2400+ (≥6 mos exp) · P1: &gt;40 contests + exp · P3: all &lt;5 contests
            </div>
            """,
            unsafe_allow_html=True,
        )

    col_btn, col_reset, _ = st.columns([1.2, 0.8, 3])
    with col_btn:
        analyze_btn = st.button("🚀 Analyze Resumes", type="primary", use_container_width=True)
    with col_reset:
        st.button("🔄 Reset", on_click=_reset_app, key="reset_top", use_container_width=True)

# --- Analysis logic ---
if analyze_btn:
    raw_lines = [line.strip() for line in urls_text.strip().splitlines() if line.strip()]
    
    urls = []
    for line in raw_lines:
        match = re.search(r"https?://[^\s<>\"\'\)\]]+", line)
        if match:
            urls.append(match.group(0).rstrip(".,;:)"))
        else:
            urls.append(line)

    if not urls:
        st.warning("Please paste at least one valid resume URL.")
        st.stop()

    results: list[dict] = []
    progress = st.progress(0, text="Starting analysis…")
    status_area = st.empty()
    current_level = st.session_state.get("selected_level", "Auto (Detect Level)")

    for i, url in enumerate(urls, 1):
        pct = (i - 1) / len(urls)
        progress.progress(pct, text=f"Processing resume {i} of {len(urls)}…")

        # Step 1 – Download & parse resume
        status_area.info(f"⬇️  Downloading & parsing [{i}/{len(urls)}]: `{url[:70]}…`")
        parsed = parse_resume(url)

        if parsed.get("error"):
            parsed["cf_stats"] = {"max_rating": None, "contests_to_max": None, "total_contests": None, "error": parsed["error"]}
            parsed["cc_stats"] = {"max_rating": None, "contests_to_max": None, "total_contests": None, "error": parsed["error"]}
            parsed["lc_stats"] = {"max_rating": None, "contests_to_max": None, "total_contests": None, "error": parsed["error"]}
            parsed["cheating_status"] = "NA"
            parsed["caught_penalties"] = []
            parsed["teaching_experience"] = {"has_experience": False, "duration_text": None}
            parsed["priority"] = "P2"
            parsed["level"] = current_level
            parsed["fitment_score"] = 0
            results.append(parsed)
            continue

        # Step 2 – Fetch profiles and check contest penalties
        status_area.info(f"📊 Checking profiles & contest integrity for **{parsed['name']}** [{i}/{len(urls)}]…")
        profiles = fetch_all_profiles(
            parsed.get("cf_handles") or parsed.get("codeforces"),
            parsed.get("cc_handles") or parsed.get("codechef"),
            parsed.get("lc_handles") or parsed.get("leetcode"),
        )

        # Step 3 – Merge API + text fallbacks + cheating status
        merged = _merge_stats(parsed, profiles)
        pf = _compute_priority_and_fitment(merged, current_level)
        merged["priority"] = pf["priority"]
        merged["level"] = pf["level"]
        merged["fitment_score"] = pf["fitment_score"]
        results.append(merged)

    progress.progress(1.0, text=f"✅ Analysis complete! Processed all {len(urls)} resumes.")
    time.sleep(0.4)
    status_area.empty()
    progress.empty()

    st.session_state["results"] = results


# ──────────────── Display results ────────────────

if "results" in st.session_state and st.session_state["results"]:
    results = st.session_state["results"]
    current_level = st.session_state.get("selected_level", "Auto (Detect Level)")
    # Recalculate priority and fitment dynamically if user switches level in selectbox
    for r in results:
        if not r.get("error"):
            pf = _compute_priority_and_fitment(r, current_level)
            r["priority"] = pf["priority"]
            r["level"] = pf["level"]
            r["fitment_score"] = pf["fitment_score"]
        else:
            r["level"] = current_level

    df = _build_results_df(results)

    st.markdown('<div class="section-divider"></div>', unsafe_allow_html=True)

    # --- Data table ---
    st.markdown("#### 📋 Results Table")
    st.dataframe(df, use_container_width=True, hide_index=True)

    # --- Download buttons ---
    st.markdown('<div class="section-divider"></div>', unsafe_allow_html=True)
    st.markdown("#### 💾 Download Results")
    dl_col1, dl_col2, dl_col3, _ = st.columns([1, 1, 1, 2])
    with dl_col1:
        st.download_button(
            "📥 Download CSV",
            data=df.to_csv(index=False),
            file_name="cp_profiles.csv",
            mime="text/csv",
            use_container_width=True,
        )
    with dl_col2:
        st.download_button(
            "📥 Download Excel",
            data=_to_excel(results),
            file_name="cp_profiles.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True,
        )
    with dl_col3:
        st.button("🔄 Reset All", on_click=_reset_app, key="reset_bottom", use_container_width=True)

# ── Footer ──
st.markdown('<div class="section-divider"></div>', unsafe_allow_html=True)
st.markdown(
    """
    <div style="text-align:center; color:#64748b; font-size:0.78rem; padding:0.5rem 0 1.5rem;">
        CP Profile Analyzer · Built with Streamlit · Checks official contest plagiarism & penalty flags · In-memory session only
    </div>
    """,
    unsafe_allow_html=True,
)
