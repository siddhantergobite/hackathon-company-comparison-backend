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

### 4. Build the UI (React)

The UI is a React app in `frontend/` (Vite + React Router). FastAPI serves the production build at `/casefile/`.

```bash
cd frontend
npm install
npm run build      # outputs frontend/dist (restart the backend after the first build)
```

`start_backend.bat` runs the build automatically on first launch. If `frontend/dist` doesn't exist, the backend falls back to the legacy static UI in `casefile/`.

**Frontend development** (hot reload, proxies `/api` to the backend on :8765):

```bash
cd frontend
npm run dev        # http://localhost:5173/casefile/
```

Set `VITE_API_BASE` (e.g. in `frontend/.env.local`) only if the UI must call a backend on a different origin.

---

## Casefile exhibits

| Exhibit | Route | Purpose |
|---------|-------|---------|
| A — Brochure | `/casefile/brochure` | Upload PDF/DOCX/image or search your company |
| B — Target Company | `/casefile/target` | Research a public company URL (leadership, POC, hiring, SWOT, finance) |
| C — Compare & Pitch | `/casefile/pitch` | Gap analysis + outreach pitch |
| D — Outreach | `/casefile/outreach` | Message drafts from pitch |
| E — Download PDF | `/casefile/export` | Full casefile export |
| F — AEO / GEO | `/casefile/aeo-geo` | Answer-engine & generative-engine visibility audit |

Your progress (brochure, target, pitch, audit, outreach log) is kept for the browser session, so a page refresh doesn't lose a long research run.

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
├── backend/events/                  # Event Hub (MongoDB): routes/, services/, collectors/, processors/, scripts/, tests/
├── frontend/                        # React UI (Vite + React Router); pages/events + pages/admin = Event Hub
│   └── src/
│       ├── pages/                   # One page per exhibit (A–F) + 404
│       ├── components/
│       │   ├── layout/              # App shell: sidebar, topbar
│       │   ├── ui/                  # Reusable primitives (Button, Card, Tabs, …)
│       │   └── brochure|target|pitch|outreach|aeo/   # Feature components
│       ├── context/                 # Casefile state + API calls, toasts
│       ├── api/client.js            # Backend requests
│       ├── utils/                   # Research-data helpers (flatten, POC, sanitize)
│       └── styles/                  # Design tokens (light/dark) + component CSS
├── casefile/                        # Legacy static UI (fallback when frontend/dist is absent)
├── start_backend.bat
├── requirements.txt
└── .env.example
```

---

## Event Hub (global event aggregator)

A second tool inside Casefile: browse, search and filter upcoming conferences, meetups, seminars, startup and networking events, open any event for full details, and manage/ingest events from an admin dashboard. It lives in the same app: API on `:8765` (`/api/events`, `/api/admin`), UI under **Event Hub** in the sidebar (`/casefile/events`, `/casefile/admin`).

- **Storage:** MongoDB, database `event_data`, collection `events` (plus `categories`, `ingestion_runs`, `ingestion_errors`).
- **Isolation:** if the packages or MongoDB are missing, the rest of Casefile keeps working; only the Event Hub endpoints answer `503`.

### Setup

```bash
# 1. dependencies (into the project's .venv)
uv pip install -r requirements.txt          # adds pymongo, pydantic-settings, pycountry

# 2. .env  (see .env.example, "Event Hub" block)
EVENT_MONGO_URI=mongodb://localhost:27017
EVENT_MONGO_DB=event_data
EVENT_ADMIN_API_KEY=<long random value>     # python -c "import secrets; print(secrets.token_urlsafe(32))"

# 3. test data (24 fictional events, dates relative to today; safe to re-run)
python -m backend.events.scripts.seed_events            # add --reset to replace them

# 4. UI build (once, and after frontend changes) + backend as usual
cd frontend && npm install && npm run build
```

Open `http://127.0.0.1:8765/casefile/events`. The admin key is only needed for `/casefile/admin` (entered in the browser, kept in `sessionStorage`).

### Pages

| Route | What |
|-------|------|
| `/casefile/events` | Discovery: search, filters (type, industry, country/state/city, date, format, price), sorting, 20/page server-side pagination. Filters live in the URL so results are shareable. |
| `/casefile/events/:slug` | Full details: about, date & time, location + map, topics, industries, audience, organizer, registration, source & last-verified. |
| `/casefile/admin` | Events table (approve / reject / edit / reprocess / mark duplicate / delete), add & edit form, duplicate review + merge, source health, ingestion errors. |

### API

| Method | Path | Notes |
|--------|------|-------|
| GET | `/api/events` | `page, limit(≤100), search, event_type, country, state, city, category, start_date, end_date, is_online, format, price_type, sort, status`. Returns `{page, limit, total, total_pages, events}`. Default: approved events that are upcoming/ongoing, soonest first. |
| GET | `/api/events/{id}` · `/api/events/slug/{slug}` | Full event (old slugs keep working after edits/merges). |
| GET | `/api/events/types` · `/categories` · `/locations` | Filter options with counts. |
| * | `/api/admin/...` | Requires `X-Admin-Key`. CRUD, `approve`, `reject`, `duplicate`, `merge`, `reprocess`, `duplicates`, `sources`, `ingestion/runs`, `ingestion/errors`, `stats`. |

Errors: `400` invalid request, `404` not found, `409` conflict, `503` database unavailable/not configured, `500` generic (details go to the server log only).

Search matches the **start of words** across title, description, organizer, city, country, category and topics, so `AI` finds AI events but not "Spain" or "training".
Dates on events are `YYYY-MM-DD` strings; status (`upcoming → ongoing → completed`) is refreshed on startup, every `EVENT_STATUS_REFRESH_MINUTES`, and after each ingestion run. `cancelled`/`postponed` are set by people and never overwritten.

### Ingestion (adding real event sources)

```
Source → Collect → Validate → Normalize → Clean → Dedupe → Classify → MongoDB
```

```bash
python -m backend.events.scripts.ingest_events --list                 # collectors + whether configured
python -m backend.events.scripts.ingest_events --source eventbrite    # run one   (--dry-run to preview)
python -m backend.events.scripts.ingest_events --all --ai             # every configured source, LLM classification
```

- **Collectors** (`backend/events/collectors/`) only fetch; they know nothing about MongoDB. Official APIs first: `eventbrite` (needs `EVENT_EVENTBRITE_TOKEN` + organization ids) and `meetup` (needs `EVENT_MEETUP_ACCESS_TOKEN` + group names). Public iCal/JSON feeds are declared in `backend/events/collectors/sources.json` (copy `sources.example.json`). Feeds honour `robots.txt`, rate limits and an honest `User-Agent`; nothing scrapes HTML. Only add sources whose terms allow it.
- **developers.events** (`developers-events`): an open list of developer conferences worldwide (~750 upcoming). Its data is **CC BY-NC 4.0: non-commercial use only, attribution required**, so it is opt-in: set `EVENT_DEVELOPERS_EVENTS_ENABLED=true` only if that fits your use, then `python -m backend.events.scripts.ingest_events --source developers-events`. Every imported event links back to the source and carries an attribution line. It provides names, dates, city/country and the official website (no images, prices or long descriptions). Re-running refreshes existing events instead of duplicating them.
- **Dedupe** (`processors/deduplicate.py`): exact match on `(source, source_event_id)`; otherwise fuzzy title + start date + city + organizer/venue. Confident matches merge into the existing event; near matches are stored as `pending` with a "possible duplicate" flag for the admin *Duplicates* tab. Numbered editions ("Meetup #7" vs "#8") are never merged.
- **Classification** (`processors/classify.py`): built-in rules always run; set `EVENT_AI_ENABLED=true` to also use Casefile's Azure OpenAI client. AI only fills missing fields and can never block storing an event.
- Ingested events that validate and have an official URL are published automatically (`EVENT_INGEST_AUTO_APPROVE=false` holds them for review). Admin-edited events are never overwritten by a source.

> The Eventbrite and Meetup collectors are written against the documented APIs and unit-tested with sample payloads; they have not been run against the live services (they need your credentials).

### Tests

```bash
python -m pytest backend/events/tests -q      # uses a throwaway database, event_data_pytest (dropped afterwards)
```

## News Intelligence (AI news aggregator)

A **News** section inside Casefile: headlines from ~48 publishers (BBC, Guardian, NPR, TechCrunch, The Hindu, NASA, Nature, OpenAI, ...), collected in the background, grouped into stories, categorised and summarised. It shares the FastAPI app, the React UI and the MongoDB server with the rest of the project (database `news_data`, collection `news`).

### Setup

```bash
# 1. dependencies (feedparser etc.; into the project's .venv)
uv pip install --python .venv\Scripts\python.exe -r requirements.txt
# 2. .env: see the "News Intelligence" block in .env.example (all optional; sensible defaults)
# 3. UI build, then run the backend as usual. The worker starts with the API and
#    fills the database within a minute or two (or: python -m backend.news.scripts.ingest_news)
cd frontend && npm run build
```

### Pages

| Path | What |
| --- | --- |
| `/casefile/news` | Dashboard: search, 20 category tabs, Top Stories, What's happening now, Latest grid with *Load more*, Trending, source/date/topic filters |
| `/casefile/news/<id>` | Story page: AI summary, what happened, key points, topics & entities, related coverage from every outlet, *Read Original Article* |
| `/casefile/news-admin` | Sign in with `NEWS_ADMIN_API_KEY` (or `EVENT_ADMIN_API_KEY`): add/edit/enable/disable/delete sources, fetch now, per-source status (active / failed / stale), categories, error log and runs |

### API

Public, under `/api/news`: `""`, `/latest`, `/trending`, `/top-stories`, `/whats-happening`, `/search?q=`, `/category/{slug}`, `/source/{name}`, `/topic/{name}`, `/story/{id}`, `/related/{id}`, `/sources`, `/categories`, `/topics`, `/{id}`. List endpoints take `page`, `limit`, `category`, `source`, `topic`, `date` (`hour|today|week|custom`) and `sort`. Admin, under `/api/admin/news` (header `X-Admin-Key`): `sources`, `categories`, `stats`, `runs`, `errors`, `enrich`, `recluster`.

### How it works

- **Collect** (`collectors/`): RSS/Atom feeds only (no HTML scraping), with conditional GET (ETag), timeouts, an honest User-Agent and exponential back-off per source. One failing source never affects the others. Reuters and AP publish no free RSS; add `NEWS_API_KEY` and enable the *Reuters & AP (via NewsAPI)* source instead.
- **Process** (`processing/`): normalise and validate, dedupe by canonical URL, cluster near-duplicate headlines into one story (`duplicate_group_id`, shown as "Covered by N sources"), rule-based category / topics / entities, importance and trending scores (recent + multi-source stories rank higher).
- **AI** (`processing/ai.py`): reuses the project's Azure OpenAI client. Only the headline and publisher teaser are sent; the model writes a summary, key points and "what happened", and anything (numbers, names, status words) not present in that text is rejected and retried, then falls back to an extractive summary. Bounded by `NEWS_AI_MAX_PER_CYCLE`. Set `NEWS_AI_ENABLED=false` to run without an LLM.
- **Copyright**: only headline, teaser, image URL and metadata are stored; every story links to the publisher. Full articles are never copied.
- **Store**: articles use string ids (`n_<sha1 of URL>`), indexed for category / source / time / topic / text search; old articles are deleted after `NEWS_RETENTION_DAYS`.

### Tests

```bash
python -m pytest backend/news/tests -q      # uses a throwaway database, news_data_pytest
```

## Notes

- Research uses public web sources only (company site, Wikipedia, Wikidata). Indian MCA / CIN / ZaubaCorp is disabled.
- Wikidata is used only when the entity’s official website matches the queried domain. It can lag (stale CEO) on some companies; the product prefers blank over a guessed replacement.
- Bot-blocked homepages (some large consumer sites) may omit officers rather than invent them.
- Optional Groq is off by default (`RESEARCH_USE_GROQ=0`) to avoid daily token caps.
