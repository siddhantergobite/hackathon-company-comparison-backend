

# Company Intelligence Casefile + AEO/GEO

Backend + Casefile UI for brochure intake, target company research, compare & pitch, outreach, PDF export, and AEO/GEO audits.

- **API:** FastAPI on `http://127.0.0.1:8765`
- **UI:** `http://127.0.0.1:8765/casefile/`
- **LLM:** Azure OpenAI primary (`gpt-5-mini`); Groq / Gemini optional fallbacks

---

## Quick Start

### 1. Install

```bash
pip install -r requirements.txt
```

### 2. Configure `.env`

Copy `.env.example` → `.env` and set:

```env
AZURE_OPENAI_ENDPOINT=https://YOUR.openai.azure.com/openai/v1
AZURE_OPENAI_API_KEY=...
AZURE_OPENAI_MODEL=gpt-5-mini
GROQ_API_KEY=           # optional
GEMINI_API_KEY=         # optional text fallback
SERPAPI_KEY=            # optional AEO SERP checks
RESEARCH_USE_GROQ=0
```

### 3. Run backend

```bash
python -m uvicorn backend.main:app --host 0.0.0.0 --port 8765 --reload
```

Or double-click `start_backend.bat`

Open: **http://127.0.0.1:8765/casefile/**

That is the only product UI (Exhibits A–F, including AEO/GEO). Do not use `localhost:3000` — that was a leftover tab from an older/other server and will look like AEO/GEO is missing.

---

## Casefile exhibits

| Exhibit | Purpose |
|---------|---------|
| A — Brochure | Upload PDF/DOCX/image or search your company |
| B — Target Company | Research a public company URL |
| F — AEO / GEO | Answer-engine & generative-engine visibility audit |
| C — Compare & Pitch | Gap analysis + outreach pitch |
| D — Outreach | Message drafts from pitch |
| E — Download PDF | Full casefile export |

---

## API

| Method | Path | Role |
|--------|------|------|
| GET | `/health` | Health + LLM status |
| GET | `/api/llm-status` | Key / model diagnostics (`?probe=1`) |
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
│   ├── main.py                 # FastAPI app
│   └── services/
│       ├── brochure_extract.py
│       ├── company_research.py
│       ├── aeo_geo.py
│       ├── pitch_generator.py
│       ├── pdf_export.py
│       ├── llm.py
│       └── llm_judge.py
├── casefile/                   # Exhibit A–F UI
├── start_backend.bat
├── requirements.txt
└── .env.example
```

---

## Notes

- Research uses public web sources only (no CIN/MCA path).
- Social-media creative studio (Streamlit image/video tools) was removed; this repo is Casefile + AEO/GEO only.
