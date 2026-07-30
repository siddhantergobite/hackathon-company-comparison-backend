"""
Outfit Swap  —  Production Service
====================================
1. Gemini 3.5 Flash Vision reads the person (gender, body, pose — NOT clothes)
2. PromptEngine builds a professional fashion photography prompt
3. Generates via Pollinations Flux-Realism HD at 768x1024 (portrait)
"""
import io
import urllib.parse
import requests

MODELS = {
    "🌟 Gemini Vision + Flux-Realism (Best)": "flux-realism",
    "⚡ Flux HD (Fast)":                       "flux",
    "🚀 Turbo (Fastest)":                      "turbo",
}


def _pollinations(prompt: str, model: str, neg: str,
                  width: int = 768, height: int = 1024) -> bytes:
    encoded = urllib.parse.quote(prompt)
    seed = abs(hash(prompt)) % 999999
    url = (
        f"https://image.pollinations.ai/prompt/{encoded}"
        f"?model={model}&width={width}&height={height}"
        f"&nologo=true&enhance=false&seed={seed}"
        f"&negative={urllib.parse.quote(neg)}"
    )
    resp = requests.get(url, timeout=180)
    if resp.status_code != 200:
        raise RuntimeError(f"Pollinations error {resp.status_code}")
    return resp.content


def run(image_bytes: bytes, outfit_prompt: str,
        model_key: str = "🌟 Gemini Vision + Flux-Realism (Best)") -> bytes:

    from backend.services.gemini_service import describe_image
    from backend.services.prompt_engine import build_outfit_swap

    # Step 1: Gemini reads the person
    person_desc = ""
    if image_bytes:
        person_desc = describe_image(
            image_bytes,
            task_hint=(
                "Describe ONLY the person's physical appearance: gender, approximate age, "
                "body type, skin tone, hair color and style, facial features, and pose. "
                "Do NOT describe their current clothing at all."
            )
        )
        print(f"[Outfit] Person: {person_desc[:80]}")

    # Step 2: Build professional fashion prompt
    pos_prompt, neg_prompt = build_outfit_swap(person_desc, outfit_prompt)
    print(f"[Outfit] Prompt: {pos_prompt[:120]}")

    model_val = MODELS.get(model_key, "flux-realism")
    return _pollinations(pos_prompt, model_val, neg_prompt)
