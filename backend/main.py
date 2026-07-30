"""
AI Creative Studio - FastAPI Backend
Run: uvicorn backend.main:app --host 0.0.0.0 --port 8765 --reload
"""
import io
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from pydantic import BaseModel
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from fastapi.staticfiles import StaticFiles

from backend.services import (
    text_to_image,
    image_to_image,
    remove_background,
    upscale,
    product_shot,
    face_swap,
    outfit_swap,
    headshot,
    text_to_video,
    image_to_video,
    video_clips,
    motion_control,
    lip_sync,
    # New content & automation services
    caption_generator,
    hashtag_generator,
    caption_image,
    bulk_schedule,
    smart_schedule,
    # Research engine
    company_research,
    brochure_extract,
    pitch_generator,
    pdf_export,
)

app = FastAPI(title="AI Creative Studio", version="2.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Best model keys — hardcoded to the highest quality free option per service
BEST = {
    "text_to_image":      "⚡ FLUX.1 Schnell (Together AI — Best Free)",
    "image_to_image":     "🌟 Smart Auto Mode (Recommended)",
    "remove_background":  "🌟 BiRefNet (Best Quality — HF API)",
    "upscale":            "Lanczos 4x (Fast, No AI)",
    "product_shot_model": "isnet (High Quality)",
    "face_swap":          "Landmark Aligned + Color Match (Best)",
    "outfit_swap":        "🌟 Gemini Vision + Flux-Realism (Best)",
    "headshot":           "rembg + PIL (Fast, No GPU)",
    "text_to_video":      "🎬 Cinematic GIF (Best Quality)",
    "image_to_video":     "Ken Burns Zoom In ⚡ Free (local)",
}


# ── Health ─────────────────────────────────────────────────────────────────────
@app.get("/health")
def health():
    from backend.services import llm as llm_client
    return {
        "status": "ok",
        "version": "2.0.0",
        "llm": llm_client.ACTIVE_MODEL_LABEL,
        "azure_configured": llm_client.azure_configured(),
    }


# ── Image Tools ────────────────────────────────────────────────────────────────

@app.post("/api/text-to-image")
async def api_text_to_image(
    prompt: str = Form(...),
    negative_prompt: str = Form(""),
    width: int = Form(1024),
    height: int = Form(1024),
    style: str = Form("photo"),
    platform: str = Form("None"),
):
    try:
        img_bytes = text_to_image.run(
            prompt,
            model_key=BEST["text_to_image"],
            negative_prompt=negative_prompt,
            width=width, height=height,
            enhance=True, style=style, platform=platform,
        )
        return Response(content=img_bytes, media_type="image/png")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/image-to-image")
async def api_image_to_image(
    file: UploadFile = File(...),
    prompt: str = Form(...),
    negative_prompt: str = Form(""),
):
    try:
        image_bytes = await file.read()
        result = image_to_image.run(
            image_bytes, prompt,
            model_key=BEST["image_to_image"],
            negative_prompt=negative_prompt,
        )
        return Response(content=result, media_type="image/png")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/remove-background")
async def api_remove_background(
    file: UploadFile = File(...),
):
    try:
        image_bytes = await file.read()
        result = remove_background.run(image_bytes, BEST["remove_background"])
        return Response(content=result, media_type="image/png")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/upscale")
async def api_upscale(
    file: UploadFile = File(...),
    scale: int = Form(4),
):
    try:
        image_bytes = await file.read()
        model_key = "Lanczos 4x (Fast, No AI)" if scale >= 4 else "Lanczos 2x (Fast, No AI)"
        result = upscale.run(image_bytes, model_key)
        return Response(content=result, media_type="image/png")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/product-shot")
async def api_product_shot(
    file: UploadFile = File(...),
    background_key: str = Form("Pure White"),
    shadow: str = Form("true"),
    custom_bg: str = Form(""),
):
    try:
        image_bytes = await file.read()
        shadow_bool = shadow.lower() not in ("false", "0", "no")
        result = product_shot.run(
            image_bytes,
            background_key=background_key,
            model_key=BEST["product_shot_model"],
            shadow=shadow_bool,
        )
        return Response(content=result, media_type="image/png")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/face-swap")
async def api_face_swap(
    source: UploadFile = File(...),
    target: UploadFile = File(...),
):
    try:
        source_bytes = await source.read()
        target_bytes = await target.read()
        result = face_swap.run(source_bytes, target_bytes, BEST["face_swap"])
        return Response(content=result, media_type="image/png")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/outfit-swap")
async def api_outfit_swap(
    file: UploadFile = File(...),
    outfit_prompt: str = Form(...),
):
    try:
        image_bytes = await file.read()
        result = outfit_swap.run(image_bytes, outfit_prompt, BEST["outfit_swap"])
        return Response(content=result, media_type="image/png")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/headshot")
async def api_headshot(
    file: UploadFile = File(...),
    style_key: str = Form("Corporate White"),
):
    try:
        image_bytes = await file.read()
        result = headshot.run(image_bytes, style_key, BEST["headshot"])
        return Response(content=result, media_type="image/png")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── Video Tools ────────────────────────────────────────────────────────────────

@app.post("/api/text-to-video")
async def api_text_to_video(
    prompt: str = Form(...),
    num_frames: int = Form(12),
    fps: int = Form(6),
):
    try:
        result = text_to_video.run(prompt, BEST["text_to_video"])
        media_type = "image/gif" if result[:3] == b"GIF" else "video/mp4"
        return Response(content=result, media_type=media_type)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/image-to-video")
async def api_image_to_video(
    file: UploadFile = File(...),
    motion: str = Form("zoom_in"),
    num_frames: int = Form(30),
    fps: int = Form(12),
):
    try:
        image_bytes = await file.read()
        # Map motion name to model key
        motion_map = {
            "zoom_in":  "Ken Burns Zoom In ⚡ Free (local)",
            "zoom_out": "Ken Burns Zoom Out ⚡ Free (local)",
            "pan_lr":   "Pan Left → Right ⚡ Free (local)",
            "pan_rl":   "Pan Right → Left ⚡ Free (local)",
            "shake":    "Camera Shake ⚡ Free (local)",
        }
        model_key = motion_map.get(motion, BEST["image_to_video"])
        result = image_to_video.run(image_bytes, model_key, num_frames, fps)
        return Response(content=result, media_type="image/gif")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/video-clips")
async def api_video_clips(
    file: UploadFile = File(...),
    operation: str = Form("Trim Video"),
    start_sec: float = Form(0),
    end_sec: float = Form(10),
    text: str = Form(""),
    fps: int = Form(5),
):
    try:
        video_bytes = await file.read()
        result = video_clips.run(
            video_bytes, operation,
            start_sec=start_sec, end_sec=end_sec,
            text=text, fps=fps,
        )
        media_type = "image/gif" if operation == "Extract Frames as GIF" else "video/mp4"
        return Response(content=result, media_type=media_type)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/motion-control")
async def api_motion_control(
    file: UploadFile = File(...),
    effect_key: str = Form("Ken Burns (Zoom In)"),
    fps: int = Form(15),
    duration_sec: int = Form(3),
):
    try:
        image_bytes = await file.read()
        result = motion_control.run(image_bytes, effect_key, fps, duration_sec)
        return Response(content=result, media_type="image/gif")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/lip-sync")
async def api_lip_sync(
    video: UploadFile = File(...),
    audio: UploadFile = File(...),
):
    try:
        video_bytes = await video.read()
        audio_bytes = await audio.read()
        result = lip_sync.run(video_bytes, audio_bytes, "LatentSync (Best — HF Space)")
        return Response(content=result, media_type="video/mp4")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ─────────────────────────────────────────────────────────────
# CONTENT TOOLS
# ─────────────────────────────────────────────────────────────

@app.post("/api/caption-generator")
async def api_caption_generator(
    topic:    str = Form(...),
    tone:     str = Form("Friendly"),
    length:   str = Form("Medium"),
    platform: str = Form("Instagram"),
):
    """Groq Llama 3.3-70B — generates 3 on-brand caption variants."""
    try:
        result = caption_generator.run(topic, tone, length, platform)
        return {"captions": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/hashtag-generator")
async def api_hashtag_generator(
    topic:    str = Form(...),
    platform: str = Form("Instagram"),
    reach:    str = Form("Balanced"),
):
    """Groq Llama 3.3-70B — generates 30 hashtags in 3 tiers."""
    try:
        result = hashtag_generator.run(topic, platform, reach)
        return {"hashtags": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/caption-image")
async def api_caption_image(
    topic:    str = Form(...),
    tone:     str = Form("Friendly"),
    platform: str = Form("Instagram"),
):
    """Groq caption + FLUX image — returns JSON with caption + base64 image."""
    try:
        from fastapi.responses import JSONResponse
        result = caption_image.run(topic, tone, platform)
        return JSONResponse(content=result)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/bulk-schedule")
async def api_bulk_schedule(
    instructions: str = Form(""),
    platforms:    str = Form("Instagram"),   # comma-separated
    time_range:   str = Form("Next 7 days"),
    tone:         str = Form("Friendly"),
):
    """Groq Llama 3.3-70B — generates complete content calendar."""
    try:
        from fastapi.responses import JSONResponse
        platform_list = [p.strip() for p in platforms.split(",") if p.strip()]
        result = bulk_schedule.run(instructions, platform_list, time_range, tone)
        return JSONResponse(content={"schedule": result})
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/smart-schedule")
async def api_smart_schedule(
    platforms:    str = Form("Instagram"),   # comma-separated
    optimize_for: str = Form("Engagement"),
    instructions: str = Form(""),
):
    """Groq Llama 3.3-70B — returns optimal posting times with reasoning."""
    try:
        from fastapi.responses import JSONResponse
        platform_list = [p.strip() for p in platforms.split(",") if p.strip()]
        result = smart_schedule.run(platform_list, optimize_for, instructions)
        return JSONResponse(content=result)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ─────────────────────────────────────────────────────────────────────────────
# COMPANY INTELLIGENCE ENGINE
# ─────────────────────────────────────────────────────────────────────────────

class CompanyResearchRequest(BaseModel):
    url: str

@app.post("/api/company-research")
async def api_company_research(req: CompanyResearchRequest):
    """
    Full company intelligence pipeline:
    Scrape → DuckDuckGo search → Azure OpenAI analysis → JSON report.
    Covers: profile, products, market, competitors, financials, employees,
            news, social media, tech stack, SWOT, content strategy.
    """
    try:
        from fastapi.responses import JSONResponse
        result = company_research.run(req.url)
        return JSONResponse(content=result)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


class BrochureSearchRequest(BaseModel):
    company_name: str


class GeneratePitchRequest(BaseModel):
    brochure: dict
    target: dict


class ExportPdfRequest(BaseModel):
    brochure: dict
    target: dict
    pitch: Optional[dict] = None


@app.post("/api/brochure-upload")
async def api_brochure_upload(file: UploadFile = File(...)):
    """Extract pitching company profile from PDF, DOCX, or image brochure."""
    try:
        from fastapi.responses import JSONResponse
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
        from fastapi.responses import JSONResponse
        result = brochure_extract.from_company_search(req.company_name)
        return JSONResponse(content=result)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/generate-pitch")
async def api_generate_pitch(req: GeneratePitchRequest):
    """Compare pitching company vs target and generate outreach pitch."""
    try:
        from fastapi.responses import JSONResponse
        result = pitch_generator.run(req.brochure, req.target)
        return JSONResponse(content=result)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/export-pdf")
async def api_export_pdf(req: ExportPdfRequest):
    """Export full casefile as PDF."""
    try:
        pdf_bytes = pdf_export.run(req.brochure, req.target, req.pitch)
        filename = "casefile-report.pdf"
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


# Casefile UI on same origin as API — fixes Chrome "Insecure download blocked"
_CASEFILE_DIR = Path(__file__).resolve().parent.parent / "casefile"
if not _CASEFILE_DIR.is_dir():
    _CASEFILE_DIR = (
        Path(__file__).resolve().parent.parent.parent
        / "hackathon_frontend_company_comparison"
        / "AI-Company-Intelligence"
    )
if _CASEFILE_DIR.is_dir():
    app.mount(
        "/casefile",
        StaticFiles(directory=str(_CASEFILE_DIR), html=True),
        name="casefile",
    )
