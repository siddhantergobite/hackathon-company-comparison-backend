"""
Image-to-Video: animate a still image with cinematic motion.
100% local, no GPU, no API key — uses PIL frame animation.
"""
import io
from PIL import Image
from backend.services.motion_control import _make_frames, EFFECTS

MODELS = {
    "Ken Burns Zoom In ⚡ Free (local)": "zoom_in",
    "Ken Burns Zoom Out ⚡ Free (local)": "zoom_out",
    "Pan Left → Right ⚡ Free (local)": "pan_lr",
    "Pan Right → Left ⚡ Free (local)": "pan_rl",
    "Camera Shake ⚡ Free (local)": "shake",
}


def run(image_bytes: bytes, model_key: str = "Ken Burns Zoom In ⚡ Free (local)",
        num_frames: int = 30, fps: int = 12) -> bytes:

    effect = MODELS.get(model_key, "zoom_in")
    img = Image.open(io.BytesIO(image_bytes)).convert("RGB").resize((512, 512), Image.LANCZOS)
    frames = _make_frames(img, effect=effect, num_frames=num_frames)

    buf = io.BytesIO()
    duration_ms = int(1000 / fps)
    frames[0].save(
        buf, format="GIF", save_all=True,
        append_images=frames[1:], loop=0,
        duration=duration_ms, optimize=False,
    )
    return buf.getvalue()
