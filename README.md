# AI Creative Studio

Full-stack AI platform for **social media content creation** and **company intelligence research**.

- Frontend: Streamlit (`http://localhost:8501`)
- Backend: FastAPI (`http://localhost:8765`)
    Models: Azure OpenAI (`gpt-5-mini`), Together AI FLUX, Gemini image fallback

---

## Quick Start

### 1. Install

```bash
pip install -r requirements.txt
```

### 2. Configure `.env`

```env
AZURE_OPENAI_ENDPOINT=https://YOUR.openai.azure.com/openai/v1
AZURE_OPENAI_API_KEY=...
AZURE_OPENAI_MODEL=gpt-5-mini
GEMINI_API_KEY=AQ....         # image generation fallback
GROQ_API_KEY=gsk_...          # optional LLM fallback
TOGETHER_API_KEY=...          # optional — better image quality
HF_TOKEN=hf_...               # optional
```

### 3. Run

**Terminal 1 — Backend**
```bash
python -m uvicorn backend.main:app --host 0.0.0.0 --port 8765 --reload
```
Or double-click `start_backend.bat`

**Terminal 2 — Frontend**
```bash
streamlit run app.py --server.port 8501
```
Or double-click `start_frontend.bat`

Open: **http://localhost:8501**

---

## Features

### Image Tools
| Tool | Engine |
|------|--------|
| Text to Image | Together FLUX.1-Schnell / SDXL + Groq prompt enhance |
| Image to Image | InstructPix2Pix |
| Remove Background | BiRefNet / rembg |
| Upscale | Lanczos + sharpening |
| Face Swap | InsightFace + OpenCV seamless clone |
| Product Shot / Outfit / Headshot | Local PIL pipelines |

### Video Tools
| Tool | Engine |
|------|--------|
| Text to Video | Pollinations / HF |
| Image to Video | Local frame animation |
| Lip Sync | LatentSync / SadTalker (HF Spaces) |
| Video Clips / Motion | moviepy / OpenCV |

### Content Tools
| Tool | Engine |
|------|--------|
| Caption Generator | Groq Llama 3.3-70B |
| Hashtag Generator | Groq Llama 3.3-70B |
| Caption + Image | Groq + FLUX |
| Bulk Schedule via AI | Groq calendar JSON |
| Smart Scheduling via AI | Groq timing strategy |

### Research — Company Intelligence
Paste any company URL → full multi-source intelligence report.

**MCP-style pipeline (multi-agent — scrapes MANY public sites, not one):**
```
URL
 │
 ├─ Site Agent         → company website + footer + /about /products /contact
 ├─ Search Agent       → find URLs on ZaubaCorp, Tofler, AmbitionBox, Glassdoor,
 │                       Justdial, IndiaMART, LinkedIn, Crunchbase, news, etc.
 ├─ Scrape Agent       → VISIT each public URL and scrape full page text + contacts
 ├─ Merge Agent        → combine emails/phones/facts from every site scraped
 ├─ Citation Agent     → Perplexity-style favicons for every site visited
 └─ Analysis Agent     → Groq openai/gpt-oss-120b → structured JSON report
```

**Report tabs:** Overview · Competitors · People & Culture · News · SWOT · Content Strategy · Risk & Finance · **Contacts**

**Contacts extraction (verified, not AI-guessed):**
- Homepage **footer** (“Get In Touch” blocks)
- `/contact`, `/contact-us`, `/get-in-touch` pages
- `mailto:` / `tel:` links
- Person name next to phone (e.g. `Suresh Shriyan: +91 98672 00065`)
- Emails with person + department labels
- Office addresses (Mumbai HQ, branch offices, etc.)

**Citations:** overlapping favicons + “N sources” → expandable source cards with clickable URLs.

**Anti-hallucination rules:**
- Leadership only from ZaubaCorp directors (never from website quotes)
- Contacts injected from scraper directly (LLM cannot invent or erase them)
- Missing data → `Not publicly available` (never fabricated)

---

## Architecture

```
Hackathon/
├── app.py                          # Streamlit UI
├── .env                            # API keys
├── requirements.txt
├── start_backend.bat
├── start_frontend.bat
├── AI_Models_Guide.xlsx
└── backend/
    ├── main.py                     # FastAPI routes
    └── services/
        ├── company_research.py     # Multi-source intelligence engine
        ├── text_to_image.py
        ├── image_to_image.py
        ├── caption_generator.py
        ├── hashtag_generator.py
        ├── caption_image.py
        ├── bulk_schedule.py
        ├── smart_schedule.py
        ├── gemini_service.py       # Groq + Gemini helpers
        ├── prompt_engine.py
        ├── image_utils.py
        ├── face_swap.py
        ├── lip_sync.py
        └── ...
```

---

## Key API Endpoints

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/health` | Backend health |
| POST | `/api/text-to-image` | Generate image |
| POST | `/api/caption-generator` | Captions |
| POST | `/api/hashtag-generator` | Hashtags |
| POST | `/api/caption-image` | Caption + image |
| POST | `/api/bulk-schedule` | Content calendar |
| POST | `/api/smart-schedule` | Posting times |
| POST | `/api/company-research` | Company intelligence (`{"url":"..."}`) |

---

## Company Intelligence — Sources Checked

| Source | What it provides |
|--------|------------------|
| Company website | Products, about, footer contacts, tech hints |
| Sub-pages | `/about`, `/products`, `/pricing`, `/careers`, `/team` |
| ZaubaCorp (MCA) | CIN, directors, capital, status, registered address |
| DuckDuckGo (20+ queries) | Competitors, funding, news, employees, contacts |
| Wikipedia | Company history |
| News articles | Full-text scrape of top results |
| Social links | LinkedIn, Instagram, Facebook, etc. |

Every claim in the UI shows **source + confidence** (High / Medium / Low).

---

## Troubleshooting

| Issue | Fix |
|-------|-----|
| `Failed to fetch dynamically imported module` | Kill all Streamlit processes, restart once, hard-refresh (`Ctrl+Shift+R`) |
| Backend offline | Start uvicorn on port **8765** |
| Contacts empty | Re-run research — contacts come from homepage footer + contact pages |
| 422 on company-research | Body must be JSON: `{"url":"https://..."}` |
| Groq errors | Check `GROQ_API_KEY` in `.env` |

```bash
# Clean restart (Windows PowerShell)
taskkill /F /IM streamlit.exe
taskkill /F /IM uvicorn.exe
python -m uvicorn backend.main:app --host 0.0.0.0 --port 8765 --reload
streamlit run app.py --server.port 8501
```

---

## License

Built for hackathon / internal demo use.
