"""
AI Service Layer — Azure OpenAI (Primary) + Groq/Gemini Fallback
================================================================
Text / vision chat: Azure OpenAI (gpt-5-mini) via backend.services.llm
Image generation: still Gemini native / Pollinations / Together (not chat)
"""
import io
import os
import time
from dotenv import load_dotenv

load_dotenv()

from backend.services import llm as llm_client

GROQ_KEY   = os.getenv("GROQ_API_KEY", "")
GEMINI_KEY = os.getenv("GEMINI_API_KEY", "")

ENHANCE_SYSTEM = (
    "You are a professional AI image prompt engineer for social media content creation. "
    "Your ONLY job: add visual detail to the user's prompt WITHOUT changing any subject, "
    "action, or intent. "
    "STRICT RULES: "
    "1. NEVER replace or remove the subjects the user mentioned. "
    "2. NEVER add subjects not in the original prompt. "
    "3. Keep the exact action and scene. "
    "4. ONLY ADD: environment, lighting, camera angle, art style, "
    "quality tags (8K, ultra HD, photorealistic, sharp focus, cinematic). "
    "5. Output 2-3 sentences max. "
    "Return ONLY the enhanced prompt, no explanation, no quotes."
)

IMAGE_MODELS_PRIORITY = [
    "gemini-3-pro-image",
    "gemini-3.1-flash-image",
    "gemini-3.1-flash-lite-image",
    "gemini-2.5-flash-image",
]


def _gemini_client():
    from google import genai
    return genai.Client(api_key=GEMINI_KEY)


def _retry(fn, retries=2, wait=8):
    for attempt in range(retries):
        try:
            return fn()
        except Exception as e:
            err = str(e)
            if "429" in err and "retryDelay" in err and attempt < retries - 1:
                delay = wait * (attempt + 1)
                print(f"[Gemini] Rate-limited, waiting {delay}s...")
                time.sleep(delay)
                continue
            raise
    raise RuntimeError("Gemini retries exhausted")


# ── Prompt Enhancement ────────────────────────────────────────────────────────

def enhance_prompt(user_prompt: str, context: str = "photo-realistic image") -> str:
    """
    Enhance prompt while strictly preserving original subjects.
    Priority: Azure OpenAI -> Gemini -> safe tag-append
    """
    try:
        enhanced = llm_client.chat(
            [
                {"role": "system", "content": ENHANCE_SYSTEM},
                {"role": "user", "content":
                    f"Context: {context}\n"
                    f"Enhance this prompt (KEEP ALL SUBJECTS EXACTLY): {user_prompt}"},
            ],
            temperature=0.6,
            max_tokens=400,
        )
        lines = [l for l in enhanced.split("\n")
                 if l.strip() and not l.lower().startswith(("here", "sure", "of course"))]
        enhanced = " ".join(lines).strip().strip('"').strip("'")
        if enhanced and len(enhanced) > 20:
            print(f"[LLM] Enhanced OK -> {enhanced[:80]}")
            return enhanced
    except Exception as e:
        print(f"[LLM enhance] {e}")

    quality = (", ultra HD 8K, photorealistic, cinematic lighting, "
               "sharp focus, professional photography, masterpiece quality")
    return user_prompt.strip().rstrip(",") + quality


# ── Image Understanding (Vision) ──────────────────────────────────────────────

def describe_image(image_bytes: bytes, task_hint: str = "") -> str:
    """
    Describe an image using vision LLM.
    Priority: Groq Llama 3.2 90B Vision -> Gemini 3.5 Flash Vision
    """
    import base64
    from PIL import Image as PILImage

    # Resize image for API efficiency
    pil = PILImage.open(io.BytesIO(image_bytes)).convert("RGB")
    if max(pil.size) > 1024:
        pil.thumbnail((1024, 1024))
    buf = io.BytesIO()
    pil.save(buf, format="JPEG", quality=85)
    img_b64 = base64.b64encode(buf.getvalue()).decode()

    prompt_text = (
        f"Describe this image concisely for AI image generation. "
        f"{task_hint} "
        f"Focus on: main subjects, their appearance, pose, colors, lighting, composition. "
        f"Return only 1-2 descriptive sentences."
    )

    # 1. Azure OpenAI vision — primary
    try:
        result = llm_client.chat_vision(prompt_text, img_b64, max_tokens=300)
        if result:
            print("[Azure Vision] Described OK")
            return result
    except Exception as e:
        print(f"[Azure Vision] {e}")

    # 2. Gemini Vision — fallback
    try:
        from google import genai
        from google.genai import types
        client = _gemini_client()

        def call():
            return client.models.generate_content(
                model="gemini-2.0-flash",
                contents=[
                    types.Part.from_bytes(data=buf.getvalue(), mime_type="image/jpeg"),
                    prompt_text,
                ],
            )

        resp = _retry(call, retries=2, wait=5)
        return resp.text.strip()
    except Exception as e:
        print(f"[Gemini vision] {e}")

    return ""


# ── Native Gemini Image Generation ───────────────────────────────────────────

def generate_image_gemini(prompt: str) -> bytes:
    """Try Gemini native image models. Falls back to Pollinations if quota blocked."""
    from google import genai
    from google.genai import types
    from PIL import Image as PILImage

    client = _gemini_client()
    last_error = None

    for model_name in IMAGE_MODELS_PRIORITY:
        try:
            print(f"[Gemini IMG] Trying {model_name}...")

            def call(m=model_name):
                return client.models.generate_content(
                    model=m,
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        response_modalities=["IMAGE", "TEXT"],
                    ),
                )

            response = _retry(call, retries=1, wait=5)
            for part in response.candidates[0].content.parts:
                if part.inline_data is not None:
                    raw = part.inline_data.data
                    pil = PILImage.open(io.BytesIO(raw)).convert("RGB")
                    out = io.BytesIO()
                    pil.save(out, format="PNG")
                    print(f"[Gemini IMG] OK {model_name} -> {len(out.getvalue())} bytes")
                    return out.getvalue()
        except Exception as e:
            last_error = e
            print(f"[Gemini IMG] {model_name} failed: {str(e)[:80]}")
            continue

    raise RuntimeError(f"All Gemini image models failed: {last_error}")


# ── Imagen 3 ──────────────────────────────────────────────────────────────────

def generate_image_imagen3(prompt: str, aspect_ratio: str = "1:1",
                            negative_prompt: str = "") -> bytes:
    from google import genai
    from google.genai import types
    from PIL import Image as PILImage

    client = _gemini_client()
    cfg = {"number_of_images": 1, "aspect_ratio": aspect_ratio}
    if negative_prompt:
        cfg["negative_prompt"] = negative_prompt

    def call():
        return client.models.generate_images(
            model="imagen-3.0-generate-002",
            prompt=prompt,
            config=types.GenerateImagesConfig(**cfg),
        )

    result = _retry(call, retries=2, wait=10)
    raw = result.generated_images[0].image.image_bytes
    pil = PILImage.open(io.BytesIO(raw)).convert("RGB")
    buf = io.BytesIO()
    pil.save(buf, format="PNG")
    return buf.getvalue()
