"""
Motion Control: apply camera motion effects to a still image using PIL + moviepy.
Supported effects: zoom-in (Ken Burns), pan left/right, shake, rotate.
"""
import io
import os
import tempfile
from PIL import Image
import numpy as np

EFFECTS = {
    "Ken Burns (Zoom In)": "zoom_in",
    "Pan Left to Right": "pan_lr",
    "Pan Right to Left": "pan_rl",
    "Zoom Out": "zoom_out",
    "Camera Shake": "shake",
}

MODELS = {
    "PIL Cinematic (No GPU)": "pil",
}


def _make_frames(img: Image.Image, effect: str, num_frames: int = 60) -> list:
    w, h = img.size
    frames = []

    for i in range(num_frames):
        t = i / max(num_frames - 1, 1)

        if effect == "zoom_in":
            scale = 1.0 + 0.3 * t
            nw, nh = int(w / scale), int(h / scale)
            left = (w - nw) // 2
            top = (h - nh) // 2
            frame = img.crop((left, top, left + nw, top + nh)).resize((w, h), Image.LANCZOS)

        elif effect == "zoom_out":
            scale = 1.3 - 0.3 * t
            nw, nh = int(w / scale), int(h / scale)
            left = (w - nw) // 2
            top = (h - nh) // 2
            frame = img.crop((left, top, left + nw, top + nh)).resize((w, h), Image.LANCZOS)

        elif effect == "pan_lr":
            max_shift = int(w * 0.25)
            shift = int(max_shift * t)
            frame = img.crop((shift, 0, shift + int(w * 0.75), h)).resize((w, h), Image.LANCZOS)

        elif effect == "pan_rl":
            max_shift = int(w * 0.25)
            shift = int(max_shift * (1 - t))
            frame = img.crop((shift, 0, shift + int(w * 0.75), h)).resize((w, h), Image.LANCZOS)

        elif effect == "shake":
            import random
            dx = random.randint(-15, 15)
            dy = random.randint(-10, 10)
            frame = img.transform(img.size, Image.AFFINE, (1, 0, dx, 0, 1, dy))

        else:
            frame = img.copy()

        frames.append(frame)

    return frames


def run(image_bytes: bytes, effect_key: str = "Ken Burns (Zoom In)", fps: int = 15, duration_sec: int = 3) -> bytes:
    img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    # Resize to 512x512 for reasonable output size
    img = img.resize((512, 512), Image.LANCZOS)

    effect = EFFECTS.get(effect_key, "zoom_in")
    num_frames = fps * duration_sec
    frames = _make_frames(img, effect, num_frames)

    buf = io.BytesIO()
    duration_per_frame = int(1000 / fps)
    frames[0].save(
        buf,
        format="GIF",
        save_all=True,
        append_images=frames[1:],
        loop=0,
        duration=duration_per_frame,
        optimize=False,
    )
    return buf.getvalue()
