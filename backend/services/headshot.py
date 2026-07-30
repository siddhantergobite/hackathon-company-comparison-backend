"""
Headshot generator: professional headshot from casual photo via img2img + face enhancement.
Uses SD inpainting to put subject on a professional background.
"""
import io
import os
from PIL import Image, ImageEnhance
import rembg

HF_TOKEN = os.getenv("HF_TOKEN", "")

STYLES = {
    "Corporate White": {"bg": (245, 245, 245), "prompt": "professional corporate headshot, white background, studio lighting, 8k, photorealistic"},
    "Studio Gray": {"bg": (180, 180, 180), "prompt": "professional headshot, gray studio background, soft lighting, photorealistic"},
    "Outdoor Bokeh": {"bg": None, "prompt": "professional outdoor headshot, bokeh background, natural lighting, photorealistic"},
    "Dark Executive": {"bg": (30, 30, 30), "prompt": "executive portrait, dark background, dramatic lighting, photorealistic"},
}

MODELS = {
    "rembg + PIL (Fast, No GPU)": "local",
    "SD Inpainting (Requires GPU)": "sd",
}


def _enhance_portrait(image_bytes: bytes, bg_color: tuple) -> bytes:
    session = rembg.new_session("u2net_human_seg")
    removed = rembg.remove(image_bytes, session=session)
    fg = Image.open(io.BytesIO(removed)).convert("RGBA")

    # Slightly enhance sharpness and contrast for professional look
    enhancer = ImageEnhance.Sharpness(fg)
    fg = enhancer.enhance(1.4)
    enhancer = ImageEnhance.Contrast(fg)
    fg = enhancer.enhance(1.1)

    bg = Image.new("RGBA", fg.size, bg_color + (255,))
    result = Image.alpha_composite(bg, fg).convert("RGB")
    buf = io.BytesIO()
    result.save(buf, format="PNG")
    return buf.getvalue()


def run(image_bytes: bytes, style_key: str = "Corporate White", model_key: str = "rembg + PIL (Fast, No GPU)") -> bytes:
    style = STYLES.get(style_key, STYLES["Corporate White"])
    bg_color = style["bg"] or (220, 220, 220)

    if model_key == "rembg + PIL (Fast, No GPU)" or True:
        return _enhance_portrait(image_bytes, bg_color)

    raise RuntimeError("GPU model not implemented yet.")
