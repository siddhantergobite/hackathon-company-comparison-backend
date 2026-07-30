"""
Production-Grade Prompt Engine
================================
Builds optimised prompts for Flux / Pollinations models.

Key principles:
  1. NEVER change the user's subject, action, or intent
  2. Structure: [subject + action] + [environment] + [lighting] + [style] + [quality]
  3. Flux/SDXL respond best to comma-separated descriptors, not long sentences
  4. Always include strong negative prompts per use-case

Each service gets its own builder that is tailored to what social-media content
creators actually need.
"""

# ── Universal quality suffix ───────────────────────────────────────────────────
_HD = (
    "ultra HD, 8K resolution, sharp focus, highly detailed, "
    "professional photography, masterpiece quality, RAW photo"
)

# ── Universal negative prompt ─────────────────────────────────────────────────
_NEG_BASE = (
    "blurry, out of focus, low quality, worst quality, jpeg artifacts, "
    "watermark, signature, text, logo, deformed, distorted, ugly, "
    "bad anatomy, extra limbs, duplicate, mutation"
)


# ─────────────────────────────────────────────────────────────────────────────
#  TEXT TO IMAGE
# ─────────────────────────────────────────────────────────────────────────────

def build_text_to_image(user_prompt: str, style: str = "photo") -> tuple[str, str]:
    """
    Returns (positive_prompt, negative_prompt) for text-to-image generation.

    Style options: photo, cinematic, portrait, product, social_media
    """
    style_tags = {
        "photo": (
            "DSLR photograph, natural lighting, bokeh background, "
            "shallow depth of field, Nikon D850"
        ),
        "cinematic": (
            "cinematic shot, dramatic lighting, movie still, "
            "anamorphic lens, film grain, color graded"
        ),
        "portrait": (
            "professional portrait, studio lighting, soft shadows, "
            "85mm lens, shallow DOF, clean background"
        ),
        "product": (
            "product photography, white background, studio lighting, "
            "commercial shoot, clean crisp edges"
        ),
        "social_media": (
            "vibrant colors, high contrast, social media optimized, "
            "trending aesthetic, eye-catching composition"
        ),
    }.get(style, "")

    positive = f"{user_prompt.strip()}, {style_tags}, {_HD}"
    negative = _NEG_BASE
    return positive, negative


# ─────────────────────────────────────────────────────────────────────────────
#  IMAGE TO IMAGE
# ─────────────────────────────────────────────────────────────────────────────

def build_image_to_image(user_prompt: str, image_description: str = "") -> tuple[str, str]:
    """Build prompt for image transformation."""
    base = image_description.strip() if image_description else ""
    transform = user_prompt.strip()

    if base:
        positive = f"{base}, transformed: {transform}, {_HD}, photorealistic"
    else:
        positive = f"{transform}, {_HD}, photorealistic"

    negative = _NEG_BASE + ", different person, different subject"
    return positive, negative


def build_background(bg_description: str) -> tuple[str, str]:
    """Build prompt specifically for background generation."""
    positive = (
        f"{bg_description.strip()}, "
        "photorealistic environment, cinematic lighting, "
        "no people, no text, no watermark, "
        f"{_HD}"
    )
    negative = _NEG_BASE + ", people, person, human, face, hands, body parts"
    return positive, negative


# ─────────────────────────────────────────────────────────────────────────────
#  OUTFIT SWAP
# ─────────────────────────────────────────────────────────────────────────────

def build_outfit_swap(person_description: str, outfit: str) -> tuple[str, str]:
    """
    Build a prompt for outfit generation.
    person_description comes from Gemini Vision (gender, body type, skin, hair, pose).
    """
    person = person_description.strip() if person_description else "a person"
    positive = (
        f"full body professional fashion photograph of {person}, "
        f"wearing {outfit.strip()}, "
        "standing pose, white studio background, "
        "fashion editorial lighting, Vogue magazine style, "
        f"{_HD}"
    )
    negative = (
        _NEG_BASE + ", nude, nsfw, revealing, transparent, "
        "wrong proportions, missing limbs, extra fingers"
    )
    return positive, negative


# ─────────────────────────────────────────────────────────────────────────────
#  HEADSHOT
# ─────────────────────────────────────────────────────────────────────────────

def build_headshot(person_description: str, style: str = "corporate") -> tuple[str, str]:
    """Build a professional headshot prompt."""
    person = person_description.strip() if person_description else "a professional"
    style_tags = {
        "corporate": "corporate executive headshot, plain light grey background, business attire",
        "linkedin": "LinkedIn profile photo, professional smile, navy blue background",
        "creative": "creative director headshot, artistic background, modern style",
        "actor": "actor headshot, dramatic lighting, dark background, cinematic",
    }.get(style, "professional headshot, clean background")

    positive = (
        f"professional headshot portrait of {person}, "
        f"{style_tags}, "
        "studio lighting, sharp eyes, natural expression, "
        f"85mm portrait lens, {_HD}"
    )
    negative = (
        _NEG_BASE + ", full body, multiple people, bad lighting, "
        "harsh shadows, red eye, closed eyes"
    )
    return positive, negative


# ─────────────────────────────────────────────────────────────────────────────
#  TEXT TO VIDEO / ANIMATED GIF
# ─────────────────────────────────────────────────────────────────────────────

def build_text_to_video(user_prompt: str) -> str:
    """Build a cinematic scene description for video/GIF generation."""
    return (
        f"{user_prompt.strip()}, "
        "cinematic scene, dynamic composition, dramatic lighting, "
        "motion blur, film grain, color graded, "
        "ultra HD, highly detailed, professional cinematography"
    )


# ─────────────────────────────────────────────────────────────────────────────
#  PRODUCT SHOT
# ─────────────────────────────────────────────────────────────────────────────

def build_product_shot(product_description: str, background: str = "white") -> tuple[str, str]:
    """Build a commercial product photography prompt."""
    positive = (
        f"{product_description.strip()}, "
        f"professional product photography, {background} background, "
        "studio lighting, soft shadows, clean composition, "
        "commercial advertisement style, "
        f"{_HD}"
    )
    negative = _NEG_BASE + ", hands, people, text overlay, price tag"
    return positive, negative


# ─────────────────────────────────────────────────────────────────────────────
#  SOCIAL MEDIA POST HELPER
# ─────────────────────────────────────────────────────────────────────────────

SOCIAL_STYLES = {
    "Instagram": "vibrant colors, high saturation, lifestyle aesthetic, square composition, trending",
    "LinkedIn":  "professional, clean, corporate, muted colors, business context",
    "Twitter/X": "bold, high contrast, eye-catching, clear focal point",
    "YouTube":   "cinematic, dramatic, thumbnail-worthy, bright and bold",
    "TikTok":    "trendy, energetic, vivid colors, vertical format, Gen-Z aesthetic",
    "Pinterest": "aesthetic, soft colors, inspirational, editorial, clean layout",
}

def add_social_style(prompt: str, platform: str = "Instagram") -> str:
    """Append platform-specific style tags to any prompt."""
    style = SOCIAL_STYLES.get(platform, "")
    if style:
        return f"{prompt.rstrip(',')}, {style}"
    return prompt
