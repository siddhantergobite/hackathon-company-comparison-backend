"""
Caption + Image Generator
==========================
Generates a matching social media caption AND a high-quality image in one shot.

Models:
  Caption / image prompt: Azure OpenAI (primary)
  Image: FLUX.1 Schnell via Together AI → Pollinations Flux-Realism fallback

Returns JSON: {"caption": "...", "image_b64": "..."}
"""
import base64
import io
import json
import os
import urllib.parse
import requests
from dotenv import load_dotenv
load_dotenv()

from backend.services import llm as llm_client

TOGETHER_KEY = os.getenv("TOGETHER_API_KEY", "")

CAPTION_SYSTEM = """You are a top social media copywriter.
Write ONE perfect caption (not 3 variants) for the given post idea.
Include relevant emojis, a strong hook, and a clear CTA.
Output ONLY the caption text, nothing else."""

IMAGE_PROMPT_SYSTEM = """You are an AI image prompt engineer for social media content.
Convert the post idea into a vivid, detailed image generation prompt.
Focus on: visual composition, lighting, style, colors, mood.
Output ONLY the image prompt, max 2 sentences, no quotes."""


def _generate_caption(topic: str, tone: str, platform: str) -> str:
    prompt = f"Platform: {platform} | Tone: {tone} | Post idea: {topic}"
    try:
        return llm_client.chat(
            [
                {"role": "system", "content": CAPTION_SYSTEM},
                {"role": "user",   "content": prompt},
            ],
            temperature=0.85,
            max_tokens=400,
        )
    except Exception as e:
        print(f"[CaptionImg] Caption LLM failed: {e}")
    return f"Check out this amazing {topic}! Drop a comment below. #trending"


def _build_image_prompt(topic: str, tone: str, platform: str) -> str:
    """Use LLM to create a perfect image prompt from the post idea."""
    prompt = f"Platform: {platform} | Tone: {tone} | Post idea: {topic}"
    try:
        return llm_client.chat(
            [
                {"role": "system", "content": IMAGE_PROMPT_SYSTEM},
                {"role": "user",   "content": prompt},
            ],
            temperature=0.7,
            max_tokens=250,
        )
    except Exception as e:
        print(f"[CaptionImg] Image prompt LLM failed: {e}")
    return f"{topic}, professional photography, vibrant colors, social media content"


def _generate_image(img_prompt: str, platform: str) -> bytes:
    """Generate image using Together AI FLUX or Pollinations fallback."""
    # Aspect ratio based on platform
    sizes = {
        "Instagram": (1024, 1024),
        "Twitter/X": (1216, 832),
        "LinkedIn":  (1216, 832),
        "TikTok":    (768, 1344),
        "Facebook":  (1216, 832),
        "Pinterest": (896, 1152),
        "YouTube":   (1344, 768),
    }
    w, h = sizes.get(platform, (1024, 1024))

    # Quality suffix
    quality = (
        ", ultra HD, sharp focus, professional photography, "
        "vibrant colors, social media optimized, masterpiece quality"
    )
    full_prompt = img_prompt + quality

    # Together AI FLUX.1 Schnell (best quality)
    if TOGETHER_KEY:
        try:
            resp = requests.post(
                "https://api.together.xyz/v1/images/generations",
                headers={"Authorization": f"Bearer {TOGETHER_KEY}", "Content-Type": "application/json"},
                json={
                    "model": "black-forest-labs/FLUX.1-schnell-Free",
                    "prompt": full_prompt,
                    "width": w, "height": h,
                    "steps": 4, "n": 1,
                    "response_format": "b64_json",
                },
                timeout=120,
            )
            if resp.status_code == 200:
                from PIL import Image
                b64 = resp.json()["data"][0]["b64_json"]
                raw = base64.b64decode(b64)
                pil = Image.open(io.BytesIO(raw)).convert("RGB")
                buf = io.BytesIO()
                pil.save(buf, format="PNG")
                print(f"[CaptionImg] Together AI FLUX OK")
                return buf.getvalue()
        except Exception as e:
            print(f"[CaptionImg] Together AI failed: {e}")

    # Pollinations fallback
    encoded = urllib.parse.quote(full_prompt)
    seed = abs(hash(full_prompt)) % 999983
    neg = "blurry, low quality, watermark, text, logo, ugly"
    url = (
        f"https://image.pollinations.ai/prompt/{encoded}"
        f"?model=flux-realism&width={w}&height={h}"
        f"&seed={seed}&nologo=true&safe=false"
        f"&negative={urllib.parse.quote(neg)}"
    )
    resp = requests.get(url, timeout=240)
    if resp.status_code != 200:
        raise RuntimeError(f"Image generation failed: {resp.status_code}")
    print(f"[CaptionImg] Pollinations fallback OK")
    return resp.content


def run(topic: str, tone: str = "Friendly",
        platform: str = "Instagram") -> dict:
    """
    Returns dict: {"caption": str, "image_b64": str}
    """
    print(f"[CaptionImg] Generating for: {topic[:60]} | {platform} | {tone}")

    # Generate caption and image prompt in parallel concepts
    caption    = _generate_caption(topic, tone, platform)
    img_prompt = _build_image_prompt(topic, tone, platform)

    print(f"[CaptionImg] Caption: {caption[:80]}")
    print(f"[CaptionImg] Image prompt: {img_prompt[:80]}")

    # Generate image
    img_bytes = _generate_image(img_prompt, platform)

    # Apply gentle sharpening
    try:
        from backend.services.image_utils import sharpen_for_display
        img_bytes = sharpen_for_display(img_bytes)
    except Exception:
        pass

    return {
        "caption":   caption,
        "image_b64": base64.b64encode(img_bytes).decode(),
    }
