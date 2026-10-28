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

        result[f"{key_prefix}_stats"] = {
            "max_rating": final_rating,
            "contests_to_max": final_contests,
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


def _build_results_df(results: list[dict]) -> pd.DataFrame:
    """Convert analysis results into a clean display DataFrame."""
    rows = []
    for idx, r in enumerate(results, 1):
        cf_handle = (r.get("cf_handles") or [None])[0] or r.get("codeforces")
        cc_handle = (r.get("cc_handles") or [None])[0] or r.get("codechef")
        lc_handle = (r.get("lc_handles") or [None])[0] or r.get("leetcode")

        cf_url = _platform_profile_url("codeforces", cf_handle)
        cc_url = _platform_profile_url("codechef", cc_handle)
        lc_url = _platform_profile_url("leetcode", lc_handle)

        rows.append(
            {
                "#": idx,
                "Name": r["name"],
                "Resume Link": r.get("url", ""),
                "Codeforces": (
                    f"{_val(r['cf_stats']['max_rating'])} in {_val(r['cf_stats']['contests_to_max'])} contests"
                ),
                "CodeChef": (
                    f"{_val(r['cc_stats']['max_rating'])} in {_val(r['cc_stats']['contests_to_max'])} contests"
                ),
                "LeetCode": (
                    f"{_val(r['lc_stats']['max_rating'])} in {_val(r['lc_stats']['contests_to_max'])} contests"
                ),
                "Contest Penalty / Caught": r.get("cheating_status") or "NA",
            }
        )
    return pd.DataFrame(rows)


def _to_excel(results: list[dict]) -> bytes:
    """
    Build Excel with 3 columns: Name | Resume link | context.
    Each candidate occupies 3 sub-rows (one per platform).
    Name and Resume link cells are merged vertically across those 3 rows.
    Each context cell is its own row with a real clickable hyperlink.
    If no handle found → shows 'platform : NA' (plain, no link).
    """
    import openpyxl
    from openpyxl.styles import Alignment, Font, PatternFill, Border, Side

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "CP Profiles"

    # ── Styles ──────────────────────────────────────────────
    header_fill = PatternFill("solid", fgColor="D9D9D9")
    thin   = Side(style="thin",   color="BFBFBF")
    medium = Side(style="medium", color="9E9E9E")
    # outer border for merged name/link cells (bottom edge drawn at last sub-row)
    inner_border  = Border(left=thin, right=thin, top=thin,   bottom=thin)
    top_border    = Border(left=thin, right=thin, top=medium, bottom=thin)
    bottom_border = Border(left=thin, right=thin, top=thin,   bottom=medium)
    only_border   = Border(left=thin, right=thin, top=medium, bottom=medium)

    link_font   = Font(color="0563C1", underline="single")
    normal_font = Font(color="000000")
    bold_font   = Font(bold=True)
    center_wrap = Alignment(horizontal="center", vertical="center", wrap_text=True)
    mid_wrap    = Alignment(vertical="center", wrap_text=True)
    mid_left    = Alignment(vertical="center", horizontal="left", wrap_text=True)

    PLATFORM_ORDER = [
        ("codeforces", "Codeforces"),
        ("codechef",   "CodeChef"),
        ("leetcode",   "LeetCode"),
    ]

    # ── Headers ─────────────────────────────────────────────
    headers = ["Name", "Resume link", "context"]
    for col_idx, h in enumerate(headers, 1):
        cell = ws.cell(row=1, column=col_idx, value=h)
        cell.font = bold_font
        cell.fill = header_fill
        cell.border = inner_border
        cell.alignment = center_wrap

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
            "codeforces": r["cf_stats"],
            "codechef":   r["cc_stats"],
            "leetcode":   r["lc_stats"],
        }

        start_row = current_row
        end_row   = current_row + 2   # 3 sub-rows per candidate

        # ── Col A: Name (merged) ─────────────────────────────
        ws.merge_cells(
            start_row=start_row, start_column=1,
            end_row=end_row,     end_column=1,
        )
        name_cell = ws.cell(row=start_row, column=1, value=r["name"])
        name_cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        name_cell.border = Border(left=medium, right=thin, top=medium, bottom=medium)

        # ── Col B: Resume link (merged) ──────────────────────
        ws.merge_cells(
            start_row=start_row, start_column=2,
            end_row=end_row,     end_column=2,
        )
        resume_url = r.get("url", "")
        link_cell = ws.cell(row=start_row, column=2, value=resume_url)
        if resume_url:
            link_cell.hyperlink = resume_url
            link_cell.font = link_font
        link_cell.alignment = Alignment(horizontal="left", vertical="center", wrap_text=True)
        link_cell.border = Border(left=thin, right=thin, top=medium, bottom=medium)

        # ── Col C: context — one sub-row per platform ────────
        for sub, (key, label) in enumerate(PLATFORM_ORDER):
            row = current_row + sub
            handle  = handles[key]
            stats   = stats_map[key]
            prof_url = _platform_profile_url(key, handle)

            has_data = (stats["max_rating"] is not None or stats["contests_to_max"] is not None)
            r_val = _val(stats["max_rating"])
            c_val = _val(stats["contests_to_max"])
            text = (
                f"{label} : {r_val} in {c_val} contest"
                if has_data else
                f"{label} : NA"
            )

            ctx_cell = ws.cell(row=row, column=3, value=text)
            if prof_url and has_data:
                ctx_cell.hyperlink = prof_url
                ctx_cell.font = link_font
            else:
                ctx_cell.font = normal_font

            # border: thicker top on first row, thicker bottom on last
            if sub == 0:
                ctx_cell.border = Border(left=thin, right=medium, top=medium, bottom=thin)
            elif sub == 2:
                ctx_cell.border = Border(left=thin, right=medium, top=thin, bottom=medium)
            else:
                ctx_cell.border = Border(left=thin, right=medium, top=thin, bottom=thin)

            ctx_cell.alignment = mid_left

        current_row += 3   # advance by 3 sub-rows

    # ── Column widths ────────────────────────────────────────
    ws.column_dimensions["A"].width = 22
    ws.column_dimensions["B"].width = 55
    ws.column_dimensions["C"].width = 42

    # ── Row heights (all data rows) ───────────────────────────
    for row_idx in range(2, ws.max_row + 1):
        ws.row_dimensions[row_idx].height = 18

    buffer = io.BytesIO()
    wb.save(buffer)
    return buffer.getvalue()


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
    )

    col_btn, col_info = st.columns([1, 3])
    with col_btn:
        analyze_btn = st.button("🚀 Analyze Resumes", type="primary", use_container_width=True)
    with col_info:
        st.caption("ℹ️  Only public profile data is used. Checks official contest plagiarism & penalty flags.")

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

    for i, url in enumerate(urls, 1):
        pct = (i - 1) / len(urls)
        progress.progress(pct, text=f"Processing resume {i} of {len(urls)}…")

        # Step 1 – Download & parse resume
        status_area.info(f"⬇️  Downloading & parsing [{i}/{len(urls)}]: `{url[:70]}…`")
        parsed = parse_resume(url)

        if parsed.get("error"):
            parsed["cf_stats"] = {"max_rating": None, "contests_to_max": None, "error": parsed["error"]}
            parsed["cc_stats"] = {"max_rating": None, "contests_to_max": None, "error": parsed["error"]}
            parsed["lc_stats"] = {"max_rating": None, "contests_to_max": None, "error": parsed["error"]}
            parsed["cheating_status"] = "NA"
            parsed["caught_penalties"] = []
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
        results.append(merged)

    progress.progress(1.0, text=f"✅ Analysis complete! Processed all {len(urls)} resumes.")
    time.sleep(0.4)
    status_area.empty()
    progress.empty()

    st.session_state["results"] = results


# ──────────────── Display results ────────────────

if "results" in st.session_state and st.session_state["results"]:
    results = st.session_state["results"]
    df = _build_results_df(results)

    st.markdown('<div class="section-divider"></div>', unsafe_allow_html=True)

    # --- Data table ---
    st.markdown("#### 📋 Results Table")
    st.dataframe(df, use_container_width=True, hide_index=True)

    # --- Download buttons ---
    st.markdown('<div class="section-divider"></div>', unsafe_allow_html=True)
    st.markdown("#### 💾 Download Results")
    dl_col1, dl_col2, _ = st.columns([1, 1, 3])
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
