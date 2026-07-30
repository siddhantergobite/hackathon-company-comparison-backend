"""
Text-to-Image  —  Production Service
======================================
Model quality stack (high → low):

1. Together AI FLUX.1-Schnell-Free  — real FLUX, free forever, excellent quality
2. Gemini Native Image              — Google native, quota-limited
3. SDXL via HuggingFace API        — free with optional HF token, strong quality
4. Pollinations Flux-Realism        — always-available fallback

Key fixes vs previous version:
  - POST-PROCESSING is now gentle (1.25/1.03/1.04) — no halos or crunchy textures
  - RESOLUTIONS use aspect-ratio-aware native sizes (not always 1024×1024)
  - TOGETHER AI gives real FLUX.1 inference (not Pollinations' hosted version)
  - SDXL via HF provides a free high-quality alternative
"""
import base64
import io
import os
import urllib.parse
import requests
from PIL import Image
from dotenv import load_dotenv

load_dotenv()

TOGETHER_KEY = os.getenv("TOGETHER_API_KEY", "")
HF_TOKEN     = os.getenv("HF_TOKEN", "")

# ── Model registry ────────────────────────────────────────────────────────────
MODELS = {
    "⚡ FLUX.1 Schnell (Together AI — Best Free)": "together_flux_schnell",
    "📸 Flux-Realism HD (Pollinations)":           "flux-realism",
    "🎨 Flux-Pro (Pollinations)":                  "flux-pro",
    "🖼️ SDXL (HuggingFace — High Quality)":        "sdxl_hf",
    "🎌 Flux-Anime (Illustration/Anime)":          "flux-anime",
    "🚀 Turbo (Fastest)":                          "turbo",
    "🔮 Gemini Native (Google AI)":                "gemini_native",
}

STYLE_OPTIONS = {
    "Photo Realistic":  "photo",
    "Cinematic":        "cinematic",
    "Portrait":         "portrait",
    "Product Shot":     "product",
    "Social Media":     "social_media",
}

PLATFORM_OPTIONS = [
    "None", "Instagram", "LinkedIn", "Twitter/X", "YouTube", "TikTok", "Pinterest"
]

# ── Native FLUX/SDXL aspect-ratio resolutions ─────────────────────────────────
# These are optimal for FLUX and SDXL — not arbitrary 1024×1024
ASPECT_RATIOS = {
    "1:1  Square (1024×1024)":      (1024, 1024),
    "4:3  Landscape (1152×896)":    (1152, 896),
    "3:4  Portrait (896×1152)":     (896,  1152),
    "3:2  Wide (1216×832)":         (1216, 832),
    "2:3  Tall (832×1216)":         (832,  1216),
    "16:9 Cinematic (1344×768)":    (1344, 768),
    "9:16 Stories/TikTok (768×1344)": (768, 1344),
}

POLLINATIONS_MODELS = {"flux-realism", "flux-pro", "flux", "flux-anime", "turbo"}

_DEFAULT_NEG = (
    "blurry, out of focus, soft focus, low quality, worst quality, jpeg artifacts, "
    "watermark, signature, text, deformed, distorted, ugly, bad anatomy, "
    "overexposed, underexposed, grainy, noisy, pixelated, washed out, plastic skin"
)


# ── Generator: Together AI FLUX.1-Schnell-Free ───────────────────────────────
def _together_flux(prompt: str, width: int, height: int) -> bytes:
    """
    Real FLUX.1-Schnell via Together AI — completely free, no credits.
    Sign up at together.ai → get API key → set TOGETHER_API_KEY in .env
    """
    if not TOGETHER_KEY:
        raise RuntimeError("TOGETHER_API_KEY not set in .env")

    resp = requests.post(
        "https://api.together.xyz/v1/images/generations",
        headers={
            "Authorization": f"Bearer {TOGETHER_KEY}",
            "Content-Type": "application/json",
        },
        json={
            "model": "black-forest-labs/FLUX.1-schnell-Free",
            "prompt": prompt,
            "width": width,
            "height": height,
            "steps": 4,
            "n": 1,
            "response_format": "b64_json",
        },
        timeout=120,
    )
    if resp.status_code != 200:
        raise RuntimeError(f"Together AI {resp.status_code}: {resp.text[:200]}")

    b64 = resp.json()["data"][0]["b64_json"]
    img_bytes = base64.b64decode(b64)

    # Convert to PNG
    pil = Image.open(io.BytesIO(img_bytes)).convert("RGB")
    buf = io.BytesIO()
    pil.save(buf, format="PNG")
    print(f"[T2I] Together AI FLUX.1-Schnell OK -> {width}x{height}")
    return buf.getvalue()


# ── Generator: SDXL via HuggingFace Inference API ────────────────────────────
def _sdxl_hf(prompt: str, negative_prompt: str, width: int, height: int) -> bytes:
    """
    SDXL via HuggingFace free inference API.
    Works without HF_TOKEN but rate limited. Set HF_TOKEN in .env for better limits.
    """
    headers = {"Content-Type": "application/json"}
    if HF_TOKEN:
        headers["Authorization"] = f"Bearer {HF_TOKEN}"

    # Clamp to SDXL-safe range
    w = min(max(width, 512), 1024)
    h = min(max(height, 512), 1024)

    payload = {
        "inputs": prompt,
        "parameters": {
            "negative_prompt": negative_prompt or _DEFAULT_NEG,
            "width": w,
            "height": h,
            "num_inference_steps": 30,
            "guidance_scale": 7.5,
        },
    }

    url = "https://api-inference.huggingface.co/models/stabilityai/stable-diffusion-xl-base-1.0"
    resp = requests.post(url, headers=headers, json=payload, timeout=180)

    if resp.status_code == 503:
        raise RuntimeError("SDXL model loading, try again in 30s")
    if resp.status_code != 200:
        raise RuntimeError(f"SDXL HF {resp.status_code}: {resp.text[:200]}")

    pil = Image.open(io.BytesIO(resp.content)).convert("RGB")
    buf = io.BytesIO()
    pil.save(buf, format="PNG")
    print(f"[T2I] SDXL HF OK -> {w}x{h}")
    return buf.getvalue()


# ── Generator: Pollinations ───────────────────────────────────────────────────
def _pollinations(prompt: str, model: str, width: int, height: int,
                  negative_prompt: str = "") -> bytes:
    encoded = urllib.parse.quote(prompt)
    seed = abs(hash(prompt)) % 999983
    neg = negative_prompt or _DEFAULT_NEG
    url = (
        f"https://image.pollinations.ai/prompt/{encoded}"
        f"?model={model}&width={width}&height={height}"
        f"&seed={seed}&nologo=true&enhance=false&safe=false"
        f"&negative={urllib.parse.quote(neg)}"
    )
    print(f"[T2I] Pollinations {model} @ {width}x{height}")
    resp = requests.get(url, timeout=240)
    if resp.status_code != 200:
        raise RuntimeError(f"Pollinations {resp.status_code}: {resp.text[:100]}")
    return resp.content


# ── Main entry point ──────────────────────────────────────────────────────────
def run(prompt: str, model_key: str,
        negative_prompt: str = "",
        width: int = 1024, height: int = 1024,
        enhance: bool = True,
        style: str = "photo",
        platform: str = "None") -> bytes:

    from backend.services.prompt_engine import build_text_to_image, add_social_style
    from backend.services.gemini_service import enhance_prompt
    from backend.services.image_utils import sharpen_for_display

    # 1. Groq/Gemini prompt enhancement (preserves exact subject)
    enhanced = enhance_prompt(prompt, context=f"{style} image for social media")

    # 2. PromptEngine: structure + style tags + HD suffix
    pos_prompt, neg_prompt = build_text_to_image(enhanced, style=style)

    # 3. Platform style
    if platform and platform != "None":
        pos_prompt = add_social_style(pos_prompt, platform)

    final_neg = negative_prompt.strip() if negative_prompt.strip() else neg_prompt

    print(f"[T2I] Prompt: {pos_prompt[:120]}...")
    print(f"[T2I] Model : {model_key} | {width}x{height}")

    model_val = MODELS.get(model_key, "together_flux_schnell")
    raw_bytes = None

    # ── Try models in quality order ──────────────────────────────────────────
    if model_val == "together_flux_schnell":
        try:
            raw_bytes = _together_flux(pos_prompt, width, height)
        except Exception as e:
            print(f"[T2I] Together AI failed ({e}), falling back to SDXL")
            try:
                raw_bytes = _sdxl_hf(pos_prompt, final_neg, width, height)
            except Exception as e2:
                print(f"[T2I] SDXL failed ({e2}), falling back to Pollinations")
                raw_bytes = _pollinations(pos_prompt, "flux-realism", width, height, final_neg)

    elif model_val == "gemini_native":
        try:
            from backend.services.gemini_service import generate_image_gemini
            raw_bytes = generate_image_gemini(pos_prompt)
        except Exception as e:
            print(f"[T2I] Gemini failed ({e}), falling back to FLUX")
            try:
                raw_bytes = _together_flux(pos_prompt, width, height)
            except Exception:
                raw_bytes = _pollinations(pos_prompt, "flux-realism", width, height, final_neg)

    elif model_val == "sdxl_hf":
        try:
            raw_bytes = _sdxl_hf(pos_prompt, final_neg, width, height)
        except Exception as e:
            print(f"[T2I] SDXL failed ({e}), falling back to Pollinations")
            raw_bytes = _pollinations(pos_prompt, "flux-realism", width, height, final_neg)

    elif model_val in POLLINATIONS_MODELS:
        raw_bytes = _pollinations(pos_prompt, model_val, width, height, final_neg)

    else:
        raw_bytes = _pollinations(pos_prompt, "flux-realism", width, height, final_neg)

    # 4. Gentle post-processing — natural professional output, no halos
    print("[T2I] Applying gentle post-processing...")
    try:
        return sharpen_for_display(raw_bytes)
    except Exception as e:
        print(f"[T2I] Post-process failed ({e}), returning raw")
        return raw_bytes
