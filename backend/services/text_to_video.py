"""
Text-to-Video / Animated GIF  —  Production Service
=====================================================
1. PromptEngine builds a cinematic scene description
2. Pollinations generates a key frame image
3. Motion control animates it into a smooth GIF

Output: animated GIF (or MP4 via Pollinations video endpoint)
"""
import io
import urllib.parse
import requests
from PIL import Image

MODELS = {
    "🎬 Cinematic GIF (Best Quality)":    "gif_realism",
    "⚡ Animated GIF (Fast)":              "gif_flux",
    "🎥 Pollinations Video MP4":           "pollinations_video",
}


def _generate_frame(prompt: str, model: str = "flux-realism") -> Image.Image:
    from backend.services.prompt_engine import build_text_to_video
    full_prompt = build_text_to_video(prompt)
    encoded = urllib.parse.quote(full_prompt)
    seed = abs(hash(prompt)) % 999999
    url = (
        f"https://image.pollinations.ai/prompt/{encoded}"
        f"?model={model}&width=768&height=432&nologo=true&seed={seed}"
        f"&negative={urllib.parse.quote('blurry, low quality, watermark, text, logo')}"
    )
    resp = requests.get(url, timeout=180)
    if resp.status_code != 200:
        raise RuntimeError(f"Frame generation failed: {resp.status_code}")
    return Image.open(io.BytesIO(resp.content)).convert("RGB")


def _make_gif(prompt: str, img_model: str = "flux-realism",
              effect: str = "zoom_in") -> bytes:
    from backend.services.motion_control import _make_frames

    img = _generate_frame(prompt, img_model)
    img = img.resize((768, 432))
    frames = _make_frames(img, effect=effect, num_frames=40)

    buf = io.BytesIO()
    frames[0].save(
        buf, format="GIF", save_all=True,
        append_images=frames[1:], loop=0, duration=50, optimize=False
    )
    return buf.getvalue()


def _pollinations_video(prompt: str) -> bytes:
    from backend.services.prompt_engine import build_text_to_video
    full_prompt = build_text_to_video(prompt)
    encoded = urllib.parse.quote(full_prompt)
    resp = requests.get(f"https://video.pollinations.ai/prompt/{encoded}", timeout=240)
    if resp.status_code != 200:
        raise RuntimeError(f"Video error {resp.status_code}")
    return resp.content


def run(prompt: str, model_key: str = "🎬 Cinematic GIF (Best Quality)") -> bytes:
    print(f"[T2V] Prompt: {prompt} | Model: {model_key}")

    if model_key == "🎥 Pollinations Video MP4":
        try:
            return _pollinations_video(prompt)
        except Exception as e:
            print(f"[T2V] Video failed ({e}), falling back to GIF")
            return _make_gif(prompt, "flux-realism", "zoom_in")

    elif model_key == "⚡ Animated GIF (Fast)":
        return _make_gif(prompt, "flux", "pan_right")

    else:
        return _make_gif(prompt, "flux-realism", "zoom_in")
