# 🏆 CP Profile Analyzer

A Streamlit web app that analyzes competitive programming profiles from resume PDF links.

---

## Features

- **Bulk Resume Analysis** – Paste multiple PDF URLs (Google Drive or direct links)
- **Auto-Extraction** – Candidate names + Codeforces / CodeChef / LeetCode handles
- **Live Stats** – Max rating and contest count from public APIs
- **Clean Dashboard** – Summary cards, per-candidate badges, full data table
- **Export** – Download results as CSV or Excel
- **Resilient** – Handles invalid URLs, missing profiles, and API failures gracefully

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
