# 🏆 CP Profile Analyzer

A Streamlit web app that analyzes competitive programming profiles from resume PDF links.

---

## Features

- **Bulk Resume Analysis** – Paste multiple PDF URLs (Google Drive, CodeChef recruiter downloads, direct HTTP)
- **Auto-Extraction** – Candidate names, CP handles, inline ratings, ICPC achievements, portfolio links, teaching experience, and graduation year
- **Live Stats & Total Contests** – Max rating, contests to peak rating, and total contests attempted across Codeforces, CodeChef, and LeetCode
- **Cheating & Integrity Detection** – Official contest plagiarism flags, MOSS penalties, and disqualification detection
- **Role-Based Shortlisting (L1, L2, L3)**:
  - **Auto-Detection**: Dynamically assigns L1, L2, or L3 per candidate (or can be fixed to a specific level).
  - **L1**: CF ≥ 1400 / CC ≥ 1600 / LC ≥ 1850 (No experience required, only rating)
    - **Fitment Score (out of 5)**: Base score is **3**
      - **+1** if candidate has ICPC achievement
      - **+1** if candidate has very high rating (CF ≥ 1600, CC ≥ 1800, or LC ≥ 2000)
    - **P3**: Caught in > 1 contest OR reached max rating in < 5 contests across all active platforms
    - **P1**: Given > 20 contests
    - **P2**: Else
  - **L2**: CF ≥ 1600 / CC ≥ 2000 / LC ≥ 2200 + ≥ 6 months experience
    - **P3**: Caught in > 1 contest OR reached max rating in < 10 contests across all active platforms
    - **P1**: Given > 30 contests AND has experience
    - **P2**: Else
  - **L3**: CF ≥ 1800 / CC ≥ 2200 / LC ≥ 2400 (or 1850+) + ≥ 6 months experience
    - **P3**: Caught in > 1 contest OR reached max rating in < 5 contests across all active platforms
    - **P1**: Given > 40 contests AND has experience
    - **P2**: Else
- **Candidate Fitment Score (0 - 5)**:
  - Starts at 5 marks
  - -1 mark if failed Criteria 1 (ratings)
  - -1 mark if failed Criteria 2 (teaching experience)
- **Formatted Excel Export**:
  - Columns: Name | Resume link | context | Resume Shortlisting Priority (P1 > P2 > P3) | Priority for (L1, L2, L3) | Candidate Fitment Score (out of 5)
  - Context format: `{Platform} : {rating} in {c} contest and attempted {t} contest in total` + direct profile link below
  - Extra sub-rows for:
    - ICPC achievements (if present)
    - Portfolio link (if present)
    - Graduation year (`Graduation Year : {year}`, if found)
    - Teaching experience (`Have teaching experience of {duration}`, if present)
  - Merged vertical columns aligned to match specification

---

## Project Structure

```
Resume analyzer/
├── app.py               # Streamlit UI & dashboard
├── pdf_parser.py        # PDF download + text extraction + username parsing
├── profile_fetcher.py   # Codeforces / CodeChef / LeetCode API calls
├── requirements.txt     # Python dependencies
└── README.md            # This file
```

---

## Setup & Run (Windows)

### 1. Install Python 3.10+

Download from [python.org](https://www.python.org/downloads/) and **check "Add Python to PATH"** during installation.

### 2. Open a terminal in the project folder

```powershell
cd "c:\Resume analyzer"
```

### 3. Create a virtual environment (recommended)

```powershell
python -m venv venv
.\venv\Scripts\activate
```

### 4. Install dependencies

```powershell
pip install -r requirements.txt
```

### 5. Run the app

```powershell
streamlit run app.py
```

The app will open automatically at **http://localhost:8501**.

---

## How to Use

1. Paste one or more resume PDF URLs into the text area (one per line).
   - **Google Drive** share links work (file must be publicly accessible or accessible to your account).
   - **Direct HTTP** links to `.pdf` files work.
2. Click **🚀 Analyze Resumes**.
3. The app will:
   - Download each PDF and extract text.
   - Identify the candidate's name.
   - Find Codeforces, CodeChef, and LeetCode usernames from URLs or labels in the resume.
   - Query the public APIs for contest stats.
4. Results appear as interactive cards and a sortable table.
5. Use the **Download CSV** / **Download Excel** buttons to export.

---

## Data Sources

| Platform   | Method                       | Endpoint / URL                                     |
|------------|------------------------------|-----------------------------------------------------|
| Codeforces | Official REST API            | `codeforces.com/api/user.rating?handle=<handle>`   |
| CodeChef   | Scrape embedded JS + fallback| `codechef.com/users/<handle>` (profile page)        |
| LeetCode   | Public GraphQL API           | `leetcode.com/graphql`                              |

All data is fetched from **public** endpoints. No login, no API keys, no data storage.

---

## Notes

- Resumes must contain identifiable CP profile URLs or labels (e.g., `Codeforces: handle` or `codeforces.com/profile/handle`).
- If a profile is not found in the resume, the column shows **NA**.
- API rate limits are respected with built-in delays between requests.
- No data is stored permanently — results exist only in the browser session.
