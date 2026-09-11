# Company Intelligence Casefile + AEO/GEO

Backend + Casefile UI for brochure intake, target-company research, compare & pitch, outreach, PDF export, and AEO/GEO audits.

- **API:** FastAPI on `http://127.0.0.1:8765`
- **UI:** `http://127.0.0.1:8765/casefile/` (also redirected from `/`)
- **LLM:** Azure OpenAI primary (`gpt-5-mini`); Groq / Gemini optional fallbacks

This repo is Casefile + AEO/GEO only. There is no Streamlit creative studio and no `localhost:3000` UI.

---

## Quick Start

### 1. Install

```bash
pip install -r requirements.txt
```

### 2. Configure `.env`

Copy `.env.example` → `.env` and set your keys:

```env
AZURE_OPENAI_ENDPOINT=https://YOUR.openai.azure.com/openai/v1
AZURE_OPENAI_API_KEY=...
AZURE_OPENAI_MODEL=gpt-5-mini

GROQ_API_KEY=              # optional
GEMINI_API_KEY=            # optional text fallback
SERPAPI_KEY=               # optional AEO SERP checks
RESEARCH_USE_GROQ=0

# Fast authentic research is the default (~30–70s for most public companies).
# Set RESEARCH_DEEP=1 only for the old multi-minute DuckDuckGo + extra LLM-judge sweep.
RESEARCH_DEEP=0
```

Never commit `.env`.

### 3. Run backend

From the repo root (PowerShell):

```powershell
python -m uvicorn backend.main:app --host 0.0.0.0 --port 8765 --reload
```

Or double-click `start_backend.bat`.

Open: **http://127.0.0.1:8765/casefile/**

Health check: **http://127.0.0.1:8765/health**

---

## Casefile exhibits

| Exhibit | Purpose |
|---------|---------|
| A — Brochure | Upload PDF/DOCX/image or search your company |
| B — Target Company | Research a public company URL (leadership, POC, hiring, SWOT, finance) |
| F — AEO / GEO | Answer-engine & generative-engine visibility audit |
| C — Compare & Pitch | Gap analysis + outreach pitch |
| D — Outreach | Message drafts from pitch |
| E — Download PDF | Full casefile export |

---

## Exhibit B — how research works

Entering a company URL does **not** only scrape that page. The pipeline:

1. In parallel: company website, Wikipedia summary, Wikidata (only if official website `P856` matches the domain).
2. Azure OpenAI structures the report from those sources.
3. An authenticity layer then **drops** junk instead of showing a confident wrong fact:
   - Current CEO / MD / President ranked above historical founders
   - Point of contact is never a historical cofounder unless they still run the company
   - Hiring keeps official careers / company ATS / LinkedIn company jobs only (keyword job-board hits are excluded)
   - Revenue needs currency **and** scale (million/billion/crore); stock-price shaped figures are rejected
   - Nested objects are flattened so the UI never shows `[object Object]`
   - Overall score is capped by source reliability — completeness is not accuracy

If a current officer or a financial figure cannot be verified, the field stays **Not publicly available** rather than being invented.

Typical latency: **~30–70 seconds** on the default path. `RESEARCH_DEEP=1` restores the slower extra web sweep.

---

## API

| Method | Path | Role |
|--------|------|------|
| GET | `/` | Redirects to `/casefile/` |
| GET | `/health` | Health + LLM status |
| GET | `/api/llm-status` | Key / model diagnostics (`?probe=1` hits Azure) |
| POST | `/api/brochure-upload` | Brochure file → profile |
| POST | `/api/brochure-search` | Company name → profile |
| POST | `/api/company-research` | `{ "url": "..." }` → target report |
| POST | `/api/aeo-geo-audit` | `{ "url": "..." }` → AEO/GEO audit |
| POST | `/api/generate-pitch` | Brochure + target → pitch |
| POST | `/api/export-pdf` | Brochure + target + pitch → PDF |

---

## Layout

```
├── backend/
│   ├── main.py                      # FastAPI app
│   └── services/
│       ├── brochure_extract.py
│       ├── company_research.py      # Exhibit B pipeline
│       ├── wikidata.py              # Domain-matched officers / HQ / revenue
│       ├── research_authenticity.py # Hiring, POC, revenue, honest scores
│       ├── llm_judge.py             # Extra LLM-as-judge (deep mode)
│       ├── aeo_geo.py
│       ├── pitch_generator.py
│       ├── pdf_export.py
│       └── llm.py
├── casefile/                        # Exhibit A–F UI
├── start_backend.bat
├── requirements.txt
└── .env.example
```

---

## Notes

- Research uses public web sources only (company site, Wikipedia, Wikidata). Indian MCA / CIN / ZaubaCorp is disabled.
- Wikidata is used only when the entity’s official website matches the queried domain. It can lag (stale CEO) on some companies; the product prefers blank over a guessed replacement.
- Bot-blocked homepages (some large consumer sites) may omit officers rather than invent them.
- Optional Groq is off by default (`RESEARCH_USE_GROQ=0`) to avoid daily token caps.
