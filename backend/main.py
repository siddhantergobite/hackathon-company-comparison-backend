"""
Company Intelligence + Casefile + AEO/GEO backend
Run: uvicorn backend.main:app --host 0.0.0.0 --port 8765 --reload

UI: http://127.0.0.1:8765/casefile/
"""
from contextlib import AsyncExitStack, asynccontextmanager
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, UploadFile, File, HTTPException
from pydantic import BaseModel
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse, Response, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from backend.services import (
    company_research,
    brochure_extract,
    pitch_generator,
    pdf_export,
    aeo_geo,
)

# Event Hub (MongoDB-backed event aggregator). Optional: if its packages are missing the
# rest of Casefile still runs and only the /api/events + /api/admin routes are absent.
try:
    from backend.events.api import lifespan as _events_lifespan, mount as _mount_events
except Exception as _exc:  # noqa: BLE001 - an optional tool must never take Casefile down
    print(f"[EventHub] disabled ({_exc.__class__.__name__}: {_exc}). If packages are missing run: pip install -r requirements.txt")
    _events_lifespan = None
    _mount_events = None

# News Intelligence (MongoDB-backed news aggregator). Optional in the same way.
try:
    from backend.news.api import lifespan as _news_lifespan, mount as _mount_news
except Exception as _exc:  # noqa: BLE001 - an optional tool must never take Casefile down
    print(f"[News] disabled ({_exc.__class__.__name__}: {_exc}). If packages are missing run: pip install -r requirements.txt")
    _news_lifespan = None
    _mount_news = None


@asynccontextmanager
async def _lifespan(app):
    """Run the startup/shutdown of every optional tool (Event Hub, News) around the app."""
    async with AsyncExitStack() as stack:
        for ls in (_events_lifespan, _news_lifespan):
            if ls:
                await stack.enter_async_context(ls(app))
        yield

app = FastAPI(
    title="Company Intelligence Casefile",
    version="3.0.0",
    description="Brochure intake, target research, pitch, PDF export, AEO/GEO audit, the Event Hub and News Intelligence.",
    lifespan=_lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

for _name, _mount in (("EventHub", _mount_events), ("News", _mount_news)):
    if _mount:
        try:
            _mount(app)
        except Exception as _exc:  # noqa: BLE001 - keep the rest of the app alive
            print(f"[{_name}] routes not mounted ({_exc.__class__.__name__}: {_exc})")


# ── Health / LLM diagnostics ─────────────────────────────────────────────────

@app.get("/")
def root():
    """Open the Casefile UI (includes Exhibit F — AEO / GEO)."""
    return RedirectResponse(url="/casefile/", status_code=307)


@app.get("/health")
def health():
    from backend.services import llm as llm_client
    st = llm_client.llm_status()
    return {
        "status": "ok",
        "version": "3.0.0",
        "product": "company-comparison-casefile",
        "llm": st.get("active_model"),
        **st,
    }


@app.get("/api/llm-status")
def api_llm_status(probe: bool = False):
    """Show which .env / Azure key the backend is using. ?probe=1 hits Azure."""
    from backend.services import llm as llm_client
    if probe:
        # Prefer Azure probe when configured
        try:
            if llm_client.azure_configured():
                text = llm_client.chat(
                    [{"role": "user", "content": 'Return JSON: {"ok":true}'}],
                    temperature=0,
                    max_tokens=40,
                    json_mode=True,
                    timeout=45.0,
                )
                return {**llm_client.llm_status(), "probe_ok": True, "sample_chars": len(text or "")}
            return llm_client.probe_groq()
        except Exception as e:
            return {**llm_client.llm_status(), "probe_ok": False, "error": str(e)[:300]}
    return llm_client.llm_status()


# ── Company research (Exhibit B) ─────────────────────────────────────────────

class CompanyResearchRequest(BaseModel):
    url: str


@app.post("/api/company-research")
async def api_company_research(req: CompanyResearchRequest):
    """Full target-company intelligence report from a public website URL."""
    try:
        result = company_research.run(req.url)
        return JSONResponse(content=result)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── AEO / GEO (Exhibit F) ────────────────────────────────────────────────────

class AeoGeoAuditRequest(BaseModel):
    url: str
    keywords: Optional[list[str]] = None
    use_serpapi: bool = False
    max_topics: int = 3
    max_serp_searches: int = 3


@app.post("/api/aeo-geo-audit")
async def api_aeo_geo_audit(req: AeoGeoAuditRequest):
    """
    One-shot AEO/GEO audit:
    crawl site → topics → who's winning → gaps → before/after fixes → GEO snapshot.
    """
    try:
        result = aeo_geo.run(
            req.url,
            keywords=req.keywords,
            use_serpapi=req.use_serpapi,
            max_topics=req.max_topics,
            max_serp_searches=req.max_serp_searches,
        )
        return JSONResponse(content=result)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── Brochure / pitch / PDF (Exhibits A, C, E) ────────────────────────────────

class BrochureSearchRequest(BaseModel):
    company_name: str


class GeneratePitchRequest(BaseModel):
    brochure: dict
    target: dict


class ExportPdfRequest(BaseModel):
    brochure: dict
    target: dict
    pitch: Optional[dict] = None
    aeo: Optional[dict] = None


@app.post("/api/brochure-upload")
async def api_brochure_upload(file: UploadFile = File(...)):
    """Extract pitching company profile from PDF, DOCX, or image brochure."""
    try:
        data = await file.read()
        if len(data) > 25 * 1024 * 1024:
            raise HTTPException(status_code=400, detail="File exceeds 25MB limit")
        result = brochure_extract.from_file(data, file.filename or "upload.pdf")
        return JSONResponse(content=result)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/brochure-search")
async def api_brochure_search(req: BrochureSearchRequest):
    """Search and extract pitching company profile from public web."""
    try:
        result = brochure_extract.from_company_search(req.company_name)
        return JSONResponse(content=result)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/generate-pitch")
async def api_generate_pitch(req: GeneratePitchRequest):
    """Compare pitching company vs target and generate outreach pitch."""
    try:
        result = pitch_generator.run(req.brochure, req.target)
        return JSONResponse(content=result)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/export-pdf")
async def api_export_pdf(req: ExportPdfRequest):
    """Export full casefile as a branded PDF (exhibits A–D, F if present)."""
    try:
        pdf_bytes = pdf_export.run(req.brochure, req.target, req.pitch, req.aeo)
        filename = pdf_export.filename_for(req.brochure, req.target)
        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"',
                "Access-Control-Expose-Headers": "Content-Disposition",
            },
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


class SPAStaticFiles(StaticFiles):
    """Serve the React build; extension-less unknown paths get index.html so client routes deep-link."""

    async def get_response(self, path, scope):
        try:
            response = await super().get_response(path, scope)
        except StarletteHTTPException as exc:
            if exc.status_code == 404 and "." not in Path(path).name:
                response = await super().get_response("index.html", scope)
            else:
                raise
        # index.html must always be revalidated (it names the current hashed bundles);
        # the hashed files under /assets never change, so they can be cached "forever".
        if path.replace("\\", "/").startswith("assets/"):  # Windows hands us backslashes
            response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
        else:
            response.headers["Cache-Control"] = "no-cache"
        return response


# Casefile UI on same origin as API: the React build (frontend/dist) when it has
# been built, otherwise the legacy static UI in casefile/.
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_REACT_DIST = _PROJECT_ROOT / "frontend" / "dist"
_LEGACY_DIR = _PROJECT_ROOT / "casefile"

if (_REACT_DIST / "index.html").is_file():
    app.mount("/casefile", SPAStaticFiles(directory=str(_REACT_DIST), html=True), name="casefile")
elif _LEGACY_DIR.is_dir():
    print("[UI] frontend/dist not found — serving legacy UI. Run: cd frontend && npm install && npm run build")
    app.mount("/casefile", StaticFiles(directory=str(_LEGACY_DIR), html=True), name="casefile")
