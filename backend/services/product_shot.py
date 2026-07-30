"""
Product Shot: remove background from product image, place on a clean/AI-generated background.
Uses rembg for bg removal + PIL compositing.
"""
import io
from PIL import Image, ImageFilter
import rembg

BACKGROUNDS = {
    "Pure White": (255, 255, 255),
    "Soft Gray": (220, 220, 220),
    "Cream": (255, 253, 240),
    "Midnight Black": (15, 15, 15),
    "Sky Blue": (173, 216, 230),
    "Warm Beige": (245, 222, 179),
}

MODELS = {
    "u2net (General)": "u2net",
    "isnet (High Quality)": "isnet-general-use",
}


def run(image_bytes: bytes, background_key: str = "Pure White", model_key: str = "isnet (High Quality)", shadow: bool = True) -> bytes:
    model_name = MODELS.get(model_key, "u2net")
    session = rembg.new_session(model_name)

    # Remove background
    removed = rembg.remove(image_bytes, session=session)
    fg = Image.open(io.BytesIO(removed)).convert("RGBA")

    # Create background
    bg_color = BACKGROUNDS.get(background_key, (255, 255, 255))
    bg = Image.new("RGBA", fg.size, bg_color + (255,))

    if shadow:
        # Simple drop shadow
        shadow_layer = Image.new("RGBA", fg.size, (0, 0, 0, 0))
        alpha = fg.split()[3]
        shadow_alpha = alpha.point(lambda p: min(p, 120))
        shadow_layer.putalpha(shadow_alpha)
        shadow_layer = shadow_layer.filter(ImageFilter.GaussianBlur(radius=12))
        # offset shadow
        offset_shadow = Image.new("RGBA", fg.size, (0, 0, 0, 0))
        offset_shadow.paste(shadow_layer, (8, 12))
        bg = Image.alpha_composite(bg, offset_shadow)

    result = Image.alpha_composite(bg, fg).convert("RGB")
    buf = io.BytesIO()
    result.save(buf, format="PNG")
    return buf.getvalue()
