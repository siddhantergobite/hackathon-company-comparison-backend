# Company Intelligence Casefile + AEO/GEO

One FastAPI + React application with three tools:

| Tool | What it does | Where |
|------|--------------|-------|
| **Casefile** (exhibits A–F) | Brochure intake, target-company research, compare & pitch, outreach, PDF export, AEO/GEO audit | `/casefile/brochure` … `/casefile/aeo-geo` |
| **Event Hub** | Aggregated conferences, meetups and seminars, with an admin dashboard | `/casefile/events`, `/casefile/admin` |
| **News Intelligence** | Headlines from ~48 publishers, grouped into stories, categorised, AI-summarised, with a source admin | `/casefile/news`, `/casefile/news-admin` |

- **API + UI:** one server on `http://127.0.0.1:8765` (UI at `/casefile/`, also redirected from `/`)
- **LLM:** Azure OpenAI primary (`gpt-5-mini`); Groq / Gemini optional fallbacks
- **Storage:** MongoDB for Event Hub and News (Casefile itself needs no database)

There is no Streamlit creative studio and no `localhost:3000` UI.

---

## Quick Start (from a fresh clone)

### Prerequisites

| Needed | For | Check |
|--------|-----|-------|
| Python 3.11+ | backend | `python --version` |
| Node.js 18+ and npm | building the UI | `node --version` |
| Azure OpenAI key | research, pitch, AI summaries | see `.env` below |
| MongoDB (local) | Event Hub and News only | see step 3 |

Casefile (exhibits A–F) works without MongoDB. If MongoDB is down, only the Event Hub and News endpoints answer `503`.

### 1. Install the backend

Run from the repo root (PowerShell shown; the project's virtualenv is `.venv`):

```powershell
python -m venv .venv                                            # or: uv venv --python 3.11
.venv\Scripts\python.exe -m pip install -r requirements.txt     # or: uv pip install --python .venv\Scripts\python.exe -r requirements.txt
```

### 2. Configure `.env`

Copy `.env.example` → `.env` and set your keys. Only the Azure block is required for Casefile:

```env
AZURE_OPENAI_ENDPOINT=https://YOUR.openai.azure.com/openai/v1
AZURE_OPENAI_API_KEY=...
AZURE_OPENAI_MODEL=gpt-5-mini

GROQ_API_KEY=              # optional
GEMINI_API_KEY=            # optional text fallback
SERPAPI_KEY=               # optional AEO SERP checks
RESEARCH_USE_GROQ=0

# Fast research is the default (~40–70 s for most public companies).
# Set RESEARCH_DEEP=1 only for the old multi-minute DuckDuckGo + extra LLM-judge sweep.
RESEARCH_DEEP=0
```

For the other tools (all optional, see the commented blocks in `.env.example`):

| Variable | Purpose |
|----------|---------|
| `EVENT_MONGO_URI`, `EVENT_MONGO_DB` | MongoDB for Event Hub (`mongodb://localhost:27017`, `event_data`) |
| `EVENT_ADMIN_API_KEY` | Password for `/casefile/admin` (long random value) |
| `NEWS_MONGO_URI`, `NEWS_MONGO_DB` | MongoDB for News (falls back to the `EVENT_*` values; DB `news_data`) |
| `NEWS_ADMIN_API_KEY` | Password for `/casefile/news-admin` (falls back to `EVENT_ADMIN_API_KEY`) |
| `NEWS_API_KEY` | NewsAPI.org key, only for the Reuters/AP source |
| `NEWS_AI_ENABLED`, `NEWS_AI_MAX_PER_CYCLE` | AI summaries on/off, and how many articles per cycle |

Generate an admin key: `python -c "import secrets; print(secrets.token_urlsafe(32))"`. **Never commit `.env`** (it is git-ignored).

### 3. Start MongoDB (Event Hub + News)

Start your local MongoDB as a Windows service (`net start MongoDB`) or run `mongod`, then confirm it answers:

```powershell
.venv\Scripts\python.exe -c "from pymongo import MongoClient; print(MongoClient('mongodb://localhost:27017', serverSelectionTimeoutMS=2000).admin.command('ping'))"
```

### 4. Build the UI (React)

The UI is a React app in `frontend/` (Vite + React Router). FastAPI serves the production build at `/casefile/`.

```powershell
cd frontend
npm install
npm run build      # writes frontend/dist; rebuild after any change under frontend/src
cd ..
```

`start_backend.bat` runs the build automatically on first launch. If `frontend/dist` doesn't exist, the backend falls back to the legacy static UI in `casefile/`.

### 5. Run the backend

```powershell
.venv\Scripts\python.exe -m uvicorn backend.main:app --host 127.0.0.1 --port 8765 --reload
```

Or double-click `start_backend.bat`, which does the same using `.venv` and opens the browser.

> Use `python -m uvicorn`, not the `uvicorn` command. On machines with Windows Device Guard, `.venv\Scripts\uvicorn.exe` is blocked ("was blocked by your organization's Device Guard policy"); running it through `python.exe` avoids that.

### 6. Open it

| What | URL |
|------|-----|
| Casefile | http://127.0.0.1:8765/casefile/ |
| Events | http://127.0.0.1:8765/casefile/events |
| Event admin | http://127.0.0.1:8765/casefile/admin |
| News | http://127.0.0.1:8765/casefile/news |
| News admin | http://127.0.0.1:8765/casefile/news-admin |
| Health check | http://127.0.0.1:8765/health |
| Interactive API docs | http://127.0.0.1:8765/docs |

**What starts automatically with the server**
- **News worker:** polls due sources every few minutes (`NEWS_WORKER_ENABLED=true`). A fresh database fills within a minute or two, and default sources and categories are created on first start.
- **Event status refresh:** upcoming/ongoing/completed is recomputed every `EVENT_STATUS_REFRESH_MINUTES`.
- **Events are not fetched automatically.** Run the ingestion command below to import them.

### Frontend development (hot reload)

```powershell
cd frontend
npm run dev        # http://localhost:5173/casefile/  (proxies /api to the backend on :8765)
```

Keep the backend running alongside it. Set `VITE_API_BASE` (e.g. in `frontend/.env.local`) only if the UI must call a backend on a different origin.

---

## Command cheat sheet

Run from the repo root unless noted. `PY` means `.venv\Scripts\python.exe`.

**Run**
```powershell
PY -m uvicorn backend.main:app --host 127.0.0.1 --port 8765 --reload   # server (API + UI + workers)
start_backend.bat                                                       # same, via the .venv, opens the browser
cd frontend; npm run dev                                                # UI dev server on :5173
cd frontend; npm run build                                              # production UI build
cd frontend; npm run preview                                            # serve the built UI locally
```

**Event Hub data**
```powershell
PY -m backend.events.scripts.ingest_events --list                       # collectors and whether each is configured
PY -m backend.events.scripts.ingest_events --source developers-events   # import ~750 developer conferences (CC BY-NC, opt-in)
PY -m backend.events.scripts.ingest_events --source eventbrite          # one source (--dry-run to preview)
PY -m backend.events.scripts.ingest_events --all --ai                   # everything configured, with LLM classification
```
`developers-events` needs `EVENT_DEVELOPERS_EVENTS_ENABLED=true`; `eventbrite` needs `EVENT_EVENTBRITE_TOKEN` and `EVENT_EVENTBRITE_ORGANIZATION_IDS` (see [Ingestion](#ingestion-adding-real-event-sources)).

**News data** (the server's worker already does this; use these to force a run)
```powershell
PY -m backend.news.scripts.ingest_news --list                           # sources and their state
PY -m backend.news.scripts.ingest_news --all                            # fetch every enabled source now
PY -m backend.news.scripts.ingest_news --source bbc-news --source nasa  # specific sources
PY -m backend.news.scripts.ingest_news --all --no-ai                    # skip AI enrichment
PY -m backend.news.scripts.ingest_news --enrich 25                      # AI-enrich the 25 most important pending articles
```

**Tests** (each suite uses a throwaway MongoDB database and drops it afterwards)
```powershell
PY -m pytest backend -q                       # everything: Event Hub + News (254 tests, about 1 to 1.5 min)
PY -m pytest backend/events/tests -q          # Event Hub only
PY -m pytest backend/news/tests -q            # News only
```

**Checks**
```powershell
curl http://127.0.0.1:8765/health                          # server up, LLM configured?
curl http://127.0.0.1:8765/api/llm-status                  # key/model diagnostics (?probe=1 calls Azure)
curl "http://127.0.0.1:8765/api/news?limit=3"              # News API
curl "http://127.0.0.1:8765/api/events?limit=3"            # Events API
curl -H "X-Admin-Key: <key>" http://127.0.0.1:8765/api/admin/news/stats   # admin API
```

**Stop or restart the server**
```powershell
Get-NetTCPConnection -LocalPort 8765 -State Listen | ForEach-Object { Stop-Process -Id $_.OwningProcess -Force }
```
The `--reload` server restarts itself on `.py` changes but **not** on `.env` changes. Stop and start it again after editing `.env`.

### Troubleshooting

| Symptom | Cause and fix |
|---------|---------------|
| `uvicorn.exe was blocked by your organization's Device Guard policy` | Run `python -m uvicorn ...` (see step 5). |
| `WinError 10013` / port 8765 already in use | Another server is running. Stop it with the command above, or use another `--port`. |
| `'vite' is not recognized` | Run `npm install` **inside `frontend/`**, not the repo root. |
| `/casefile/` shows the old UI, or a blank page | Run `npm run build` in `frontend/`, restart the server, hard-refresh (Ctrl+F5). |
| Events / News say "unavailable" (503) | MongoDB isn't running or `EVENT_MONGO_URI` is wrong (step 3). Casefile still works. |
| Events page is empty | Events are not auto-imported. Run the `ingest_events` command above. |
| News page is empty right after first start | Wait 1–2 minutes for the first worker cycle, or run `ingest_news --all`. |
| Reuters / AP missing from News | Set `NEWS_API_KEY`, restart, then enable "Reuters & AP (via NewsAPI)" in News Admin. Its free plan is 100 requests a day, so set its poll to 60 minutes. |
| News admin / Event admin rejects the key | It must equal `NEWS_ADMIN_API_KEY` (or `EVENT_ADMIN_API_KEY`) in `.env`, and the server must have been restarted after you set it. |
| Brochure search: "Could not read the website…" | The site couldn't be fetched (offline, blocked, or JS-only). Nothing is guessed. Use the exact URL or upload a brochure. |
| Research is slow | Target research takes about 40–70 s normally. Keep `RESEARCH_DEEP=0`. |

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

> **Outreach (D) does not send email.** *Send email* only records the message in the outreach log ("demo, no mail server configured"). Connect a mail provider (SMTP, SendGrid, Gmail API) before relying on it.
>
> **Brochure search never guesses.** If almost nothing can be read from the company's site (offline, blocked, JS-only), it answers "Could not read the website" instead of inventing a profile.

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

Typical latency: **~40–70 seconds** on the default path. The hiring, leadership and evidence lookups run in the background while the main LLM call is in flight, and all contact-page candidates are fetched in one wave. `RESEARCH_DEEP=1` restores the slower extra web sweep.

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
| GET | `/docs` | Interactive OpenAPI docs for every route |

The Event Hub (`/api/events`, `/api/admin`) and News (`/api/news`, `/api/admin/news`) APIs are documented in their own sections below.

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
├── backend/common/                  # Shared by Event Hub + News: error mapping (HubRoute), polite HTTP client
├── backend/events/                  # Event Hub (MongoDB): routes/, services/, collectors/, processors/, scripts/, tests/
├── backend/news/                    # News Intelligence (MongoDB): collectors/, processing/, services/, routes/, scripts/, tests/
├── frontend/                        # React UI (Vite + React Router); pages/events + pages/admin = Event Hub, pages/news = News
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

# 3. real events: import the open developers.events list (needs EVENT_DEVELOPERS_EVENTS_ENABLED=true)
python -m backend.events.scripts.ingest_events --source developers-events
#    (optional, demo only: 24 FICTIONAL events; skip this on a real install)
#    python -m backend.events.scripts.seed_events

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
- HTTPS is verified against the operating-system certificate store (`truststore`), so sites that send an incomplete certificate chain (fine in a browser) can still be read. Certificate checking stays on.
- `seed_events` creates fictional demo events. Delete them with `db.events.deleteMany({"source.name": "Seed Data"})` in `mongosh`, or never run it.
