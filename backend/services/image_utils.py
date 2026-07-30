"""
Shared image post-processing utilities.

TUNED for natural, professional output — NOT over-sharpened.
Values based on standard photo-editing practice:
  Sharpness 1.25 / Contrast 1.03 / Color 1.04
"""
import io
from PIL import Image, ImageFilter, ImageEnhance


def sharpen_for_display(image_bytes: bytes,
                        sharpen: float = 1.25,
                        contrast: float = 1.03,
                        color: float = 1.04) -> bytes:
    """
    Gentle professional sharpening — removes AI softness without creating halos.

    Previous values (2.4 / 1.08 / 1.10) were too aggressive and created:
      - halo edges, crunchy skin, noisy textures, fake HDR look
    These values produce clean, natural output suitable for client presentation.
    """
    try:
        img = Image.open(io.BytesIO(image_bytes)).convert("RGB")

        # Mild unsharp mask to recover generation softness
        img = img.filter(ImageFilter.UnsharpMask(radius=0.8, percent=80, threshold=3))

        # Natural sharpness — just enough to remove AI blur
        img = ImageEnhance.Sharpness(img).enhance(sharpen)

        # Subtle contrast lift
        img = ImageEnhance.Contrast(img).enhance(contrast)

        # Gentle colour boost — keeps skin tones natural
        img = ImageEnhance.Color(img).enhance(color)

        buf = io.BytesIO()
        img.save(buf, format="PNG", optimize=False, compress_level=1)
        return buf.getvalue()
    except Exception as e:
        print(f"[ImageUtils] Post-process failed: {e}")
        return image_bytes


def ensure_png(image_bytes: bytes) -> bytes:
    try:
        img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()
    except Exception:
        return image_bytes
