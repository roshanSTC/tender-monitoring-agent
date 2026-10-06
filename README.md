# TenderPulse: Autonomous Tender Monitoring Agent 🛡️

An intelligent, autonomous AI agent system designed to monitor, parse, qualify, and track government and private procurement opportunities across Indian procurement portals (e.g., **GeM - Government e-Marketplace** and **CPPP / eProcure**).

---

## 🚀 Features

1. **Autonomous Discovery & Radar:**
   - Multi-portal ingestion (GeM & CPPP).
   - Monitors bid numbers, organization/ministry, tender valuation, EMD, and closing deadlines.

2. **Intelligent Eligibility Scoring:**
   - Evaluates tender requirements against your company profile (turnover thresholds, max EMD liquidity, ISO certifications, years of operating experience).
   - Generates an instant **Match Score (0–100%)** and qualification status (`Qualified`, `Review Needed`, `Disqualified`).

3. **1-Page AI Executive Summary & Risk Detection:**
   - Distills 100+ page tenders into key commercial and technical bullet points.
   - Automatically flags high-risk clauses (Liquidated Damages, PBG percentages, debarment clauses).
   - Prepares a mandatory compliance exhibits checklist.

4. **Custom PDF Document Upload & Analysis:**
   - Upload any Notice Inviting Tender (NIT) or RFP PDF to immediately run automated eligibility extraction.

5. **Corrigendum & Addendum Watchdog:**
   - Tracks amended submission dates, altered technical specs, and pre-bid clarifications.

6. **Interactive Company Baseline Manager:**
   - Adjust turnover, certifications, and experience in real-time with one-click instant recalculation across all monitored tenders.

---

## 📦 Quick Start Guide

### 1. Activate Environment & Run Dashboard

From the project root directory:

```powershell
# Activate the virtual environment
.\venv\Scripts\Activate.ps1

# Launch the Streamlit Web Application
streamlit run app.py
```

Open your browser at `http://localhost:8501`.

---

## 🗂️ Project Structure

```
d:\+\Roshan\Agent\
├── app.py                     # Streamlit Web Dashboard
├── requirements.txt           # Project dependencies
├── config/
│   ├── settings.py            # App paths and settings
│   └── company_profile.json   # Bidder baseline (Turnover, Certifications, EMD limit)
├── core/
│   ├── models.py              # Pydantic data schemas
│   ├── database.py            # SQLite persistence manager
│   ├── document_parser.py     # PDF & section extraction engine
│   ├── analyzer.py            # Eligibility matching & risk detection engine
│   ├── scraper.py             # GeM & CPPP crawler/feeder
│   └── notifier.py            # Multi-channel alert dispatch (Slack/Teams/WhatsApp)
└── data/
    ├── tenders.db             # SQLite database storing tracked tenders
    ├── sample_tender_gem.pdf  # Ready-to-test sample Indian GeM NIT document
    └── generate_sample_pdf.py # Test PDF generator
```

