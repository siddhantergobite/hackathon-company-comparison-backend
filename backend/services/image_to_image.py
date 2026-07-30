"""
Image-to-Image — Smart Transformation Engine (Fixed)
=====================================================
Previous problem: "img2img" was actually caption → text-to-image.
  Gemini describes image → Pollinations generates NEW image from description
  = identity is lost, faces change, composition changes.

Fixed architecture:
  1. BACKGROUND REPLACE  — rembg removes bg → Pollinations generates new bg
                            → PIL composites original subject (identity preserved)
  2. REAL IMG2IMG        — HF InstructPix2Pix API (actual image conditioning)
                            Takes the input image + text instruction, modifies it
  3. STYLE TRANSFER      — InstructPix2Pix with style instruction
  4. FLUX TRANSFORM      — Describe + generate (last resort when API unavailable)

Auto-detection from prompt keywords determines the best mode.
"""
import base64
import io
import os
import re
import urllib.parse
import requests
from PIL import Image
from dotenv import load_dotenv

load_dotenv()

HF_TOKEN     = os.getenv("HF_TOKEN", "")
TOGETHER_KEY = os.getenv("TOGETHER_API_KEY", "")

MODELS = {
    "🌟 Smart Auto Mode (Recommended)":          "auto",
    "🖼️ Background Replace (Preserve Subject)":   "bg_replace",
    "🔄 Real Img2Img (HF InstructPix2Pix)":       "instruct_pix2pix",
    "🎨 Style Transfer (InstructPix2Pix)":        "style_ip2p",
    "📸 Flux-Realism (Describe + Generate)":      "flux-realism",
}

BG_KEYWORDS = {
    "background", "bg", "scene", "place", "setting", "environment",
    "forest", "beach", "ocean", "mountain", "city", "space", "sunset",
    "sunrise", "studio", "indoor", "outdoor", "sky", "jungle", "desert",
    "snow", "rain", "night", "day", "room", "field", "nature", "park",
    "street", "office", "wall", "behind",
}

STYLE_KEYWORDS = {
    "anime", "cartoon", "ghibli", "pixar", "3d", "sketch", "drawing",
    "painting", "watercolor", "oil paint", "comic", "manga", "vintage",
    "retro", "neon", "cyberpunk", "impressionist", "abstract", "illustration",
}


def _detect_mode(prompt: str) -> str:
    words = set(re.findall(r'\w+', prompt.lower()))
    if words & BG_KEYWORDS:
        return "bg_replace"
    if words & STYLE_KEYWORDS:
        return "style_ip2p"
    return "instruct_pix2pix"


def _pollinations(prompt: str, model: str, width: int, height: int,
                  negative_prompt: str = "") -> bytes:
    encoded = urllib.parse.quote(prompt)
    seed = abs(hash(prompt)) % 999999
    url = (f"https://image.pollinations.ai/prompt/{encoded}"
           f"?model={model}&width={width}&height={height}"
           f"&nologo=true&enhance=false&seed={seed}")
    if negative_prompt:
        url += f"&negative={urllib.parse.quote(negative_prompt)}"
    resp = requests.get(url, timeout=240)
    if resp.status_code != 200:
        raise RuntimeError(f"Pollinations {resp.status_code}")
    return resp.content


def _background_replace(image_bytes: bytes, bg_prompt: str, w: int, h: int) -> bytes:
    """
    Pixel-perfect background replacement.
    The original subject is composited onto a new AI-generated background.
    Subject identity is 100% preserved — it's the original pixels.
    """
    from rembg import remove as rembg_remove

    print("[I2I BG] Removing background with rembg...")
    fg_rgba = rembg_remove(image_bytes)
    fg = Image.open(io.BytesIO(fg_rgba)).convert("RGBA").resize((w, h))

    print(f"[I2I BG] Generating new background: {bg_prompt[:60]}")
    bg_q = (
        f"{bg_prompt}, ultra HD, photorealistic, 8K, cinematic lighting, "
        f"detailed environment, no people, no text, no watermark"
    )
    neg = "people, person, human, face, hands, body parts, text, watermark, logo"
    bg_bytes = _pollinations(bg_q, "flux-realism", w, h, neg)
    bg = Image.open(io.BytesIO(bg_bytes)).convert("RGBA").resize((w, h))

    print("[I2I BG] Compositing...")
    result = Image.alpha_composite(bg, fg).convert("RGB")
    buf = io.BytesIO()
    result.save(buf, format="PNG")
    return buf.getvalue()


def _instruct_pix2pix(image_bytes: bytes, instruction: str,
                       image_guidance: float = 1.5,
                       text_guidance: float = 7.5) -> bytes:
    """
    Real image-to-image via HuggingFace InstructPix2Pix.
    This ACTUALLY conditions on the input image — identity is much better preserved.

    vs. previous approach (describe image → generate new image):
      OLD: caption → text2img  = totally new image, face/identity lost
      NEW: image + instruction → modified image  = original preserved, changes applied
    """
    headers = {"Content-Type": "application/json"}
    if HF_TOKEN:
        headers["Authorization"] = f"Bearer {HF_TOKEN}"

    # Resize for API efficiency
    pil = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    pil.thumbnail((512, 512))
    buf = io.BytesIO()
    pil.save(buf, format="JPEG", quality=90)
    img_b64 = base64.b64encode(buf.getvalue()).decode()

    payload = {
        "inputs": instruction,
        "parameters": {
            "image": img_b64,
            "image_guidance_scale": image_guidance,
            "guidance_scale": text_guidance,
            "num_inference_steps": 20,
        },
    }

    url = "https://api-inference.huggingface.co/models/timbrooks/instruct-pix2pix"
    print(f"[I2I] InstructPix2Pix: '{instruction[:60]}'")
    resp = requests.post(url, headers=headers, json=payload, timeout=180)

    if resp.status_code == 503:
        raise RuntimeError("Model loading, please wait 30s and retry")
    if resp.status_code != 200:
        raise RuntimeError(f"InstructPix2Pix {resp.status_code}: {resp.text[:200]}")

    result = Image.open(io.BytesIO(resp.content)).convert("RGB")
    out = io.BytesIO()
    result.save(out, format="PNG")
    print("[I2I] InstructPix2Pix OK")
    return out.getvalue()


def _style_transfer_ip2p(image_bytes: bytes, style_prompt: str) -> bytes:
    """
    Style transfer using InstructPix2Pix with high image guidance.
    High image_guidance_scale keeps identity; style is applied on top.
    """
    instruction = f"Make this image look like {style_prompt}"
    # Higher image_guidance = more faithful to original
    return _instruct_pix2pix(image_bytes, instruction,
                              image_guidance=1.8, text_guidance=6.0)


def run(image_bytes: bytes, prompt: str,
        model_key: str = "🌟 Smart Auto Mode (Recommended)",
        strength: float = 0.75, negative_prompt: str = "") -> bytes:

    from backend.services.image_utils import sharpen_for_display

    orig = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    w = min(max(round(orig.width  / 64) * 64, 512), 1152)
    h = min(max(round(orig.height / 64) * 64, 512), 1152)

    model_val = MODELS.get(model_key, "auto")

    if model_val == "auto":
        model_val = _detect_mode(prompt)
        print(f"[I2I] Auto-detected mode: {model_val}")

    raw = None

    # ── Background Replace — best mode, pixel-perfect identity preservation ──
    if model_val == "bg_replace":
        raw = _background_replace(image_bytes, prompt, w, h)
        return sharpen_for_display(raw, sharpen=1.1, contrast=1.02, color=1.03)

    # ── Real Img2Img via InstructPix2Pix ────────────────────────────────────
    if model_val == "instruct_pix2pix":
        try:
            raw = _instruct_pix2pix(image_bytes, prompt)
            return sharpen_for_display(raw)
        except Exception as e:
            print(f"[I2I] InstructPix2Pix failed ({e}), falling back to describe+generate")
            # Fall through to describe+generate

    # ── Style Transfer via InstructPix2Pix ──────────────────────────────────
    if model_val == "style_ip2p":
        try:
            raw = _style_transfer_ip2p(image_bytes, prompt)
            return sharpen_for_display(raw)
        except Exception as e:
            print(f"[I2I] Style IP2P failed ({e}), falling back to describe+generate")
            # Fall through

    # ── Describe + Generate fallback (when APIs unavailable) ─────────────────
    try:
        from backend.services.gemini_service import describe_image
        desc = describe_image(image_bytes, task_hint=prompt)
        neg = "blurry, low quality, deformed, different person, identity changed"
        quality = ", ultra HD 8K, photorealistic, sharp focus, masterpiece"
        full = f"{desc}, {prompt}{quality}" if desc else f"{prompt}{quality}"
    except Exception:
        full = f"{prompt}, ultra HD 8K, photorealistic, sharp focus"
        neg = "blurry, low quality"

    raw = _pollinations(full, "flux-realism", w, h, neg)
    return sharpen_for_display(raw)
