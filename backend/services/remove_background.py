"""
Background Removal Service
===========================
Models (quality order):
  1. BiRefNet via HF API — state-of-the-art matting, much better than rembg
                           for hair, transparent objects, fine edges
  2. rembg isnet-general — strong local model (no network needed)
  3. rembg u2net-human   — best local option for people
  4. rembg u2net         — fast general purpose

BiRefNet is from ZhengPeng7 and consistently outperforms U2Net/ISNet
especially for portrait hair, glass, and complex edges.
"""
import io
import base64
import os
import requests
from PIL import Image

HF_TOKEN = os.getenv("HF_TOKEN", "")

MODELS = {
    "🌟 BiRefNet (Best Quality — HF API)":    "birefnet_hf",
    "isnet (High Quality — Local)":            "isnet-general-use",
    "u2net Human Seg (People — Local)":        "u2net_human_seg",
    "u2net (General — Fast Local)":            "u2net",
    "u2netp (Lightweight — Fastest)":          "u2netp",
}


def _birefnet_hf(image_bytes: bytes) -> bytes:
    """
    BiRefNet via HuggingFace Inference API.
    Returns RGBA PNG with transparent background.
    """
    headers = {}
    if HF_TOKEN:
        headers["Authorization"] = f"Bearer {HF_TOKEN}"

    # Resize for API if needed
    pil = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    if max(pil.size) > 1024:
        pil.thumbnail((1024, 1024))
    buf = io.BytesIO()
    pil.save(buf, format="PNG")
    img_bytes = buf.getvalue()

    # Try ZhengPeng7/BiRefNet on HF
    url = "https://api-inference.huggingface.co/models/ZhengPeng7/BiRefNet"
    resp = requests.post(url, headers=headers, data=img_bytes,
                         timeout=120, params={"task": "image-segmentation"})

    if resp.status_code == 503:
        raise RuntimeError("BiRefNet loading, retry in 20s")
    if resp.status_code != 200:
        raise RuntimeError(f"BiRefNet HF {resp.status_code}: {resp.text[:150]}")

    # HF returns the mask PNG; we need to composite it
    mask = Image.open(io.BytesIO(resp.content)).convert("L")
    orig = pil.convert("RGBA")
    orig.putalpha(mask)
    out = io.BytesIO()
    orig.save(out, format="PNG")
    print("[BG] BiRefNet OK")
    return out.getvalue()


def _rembg_local(image_bytes: bytes, model_name: str) -> bytes:
    """Local rembg fallback."""
    import rembg
    session = rembg.new_session(model_name)
    return rembg.remove(image_bytes, session=session)


def run(image_bytes: bytes, model_key: str = "isnet (High Quality — Local)") -> bytes:
    model_name = MODELS.get(model_key, "isnet-general-use")

    if model_name == "birefnet_hf":
        try:
            return _birefnet_hf(image_bytes)
        except Exception as e:
            print(f"[BG] BiRefNet failed ({e}), falling back to isnet local")
            return _rembg_local(image_bytes, "isnet-general-use")

    return _rembg_local(image_bytes, model_name)
