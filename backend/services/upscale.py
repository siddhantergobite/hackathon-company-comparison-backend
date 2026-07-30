"""
Image Upscaling service using free open models.
- Real-ESRGAN via Hugging Face (CPU/GPU local)
- Fallback: PIL Lanczos 4x
"""
import io
import os
import requests
from PIL import Image

HF_TOKEN = os.getenv("HF_TOKEN", "")

MODELS = {
    "Real-ESRGAN x4 (Best Quality)": "ai-forever/Real-ESRGAN",
    "Lanczos 4x (Fast, No AI)": "lanczos",
    "Lanczos 2x (Fast, No AI)": "lanczos2x",
}


def _upscale_lanczos(image_bytes: bytes, scale: int = 4) -> bytes:
    from PIL import ImageFilter, ImageEnhance
    img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    new_size = (img.width * scale, img.height * scale)
    upscaled = img.resize(new_size, Image.LANCZOS)
    # Post-sharpen after upscale to recover detail
    upscaled = upscaled.filter(ImageFilter.UnsharpMask(radius=1.0, percent=110, threshold=2))
    upscaled = ImageEnhance.Sharpness(upscaled).enhance(1.8)
    upscaled = ImageEnhance.Contrast(upscaled).enhance(1.05)
    buf = io.BytesIO()
    upscaled.save(buf, format="PNG")
    return buf.getvalue()


def _upscale_real_esrgan(image_bytes: bytes) -> bytes:
    try:
        from basicsr.archs.rrdbnet_arch import RRDBNet
        from realesrgan import RealESRGANer
        import numpy as np
        import cv2

        model = RRDBNet(num_in_ch=3, num_out_ch=3, num_feat=64, num_block=23, num_grow_ch=32, scale=4)
        upsampler = RealESRGANer(scale=4, model_path=None, model=model, tile=0, tile_pad=10, pre_pad=0, half=False)
        img_array = np.array(Image.open(io.BytesIO(image_bytes)).convert("RGB"))
        img_bgr = cv2.cvtColor(img_array, cv2.COLOR_RGB2BGR)
        output, _ = upsampler.enhance(img_bgr, outscale=4)
        output_rgb = cv2.cvtColor(output, cv2.COLOR_BGR2RGB)
        result = Image.fromarray(output_rgb)
        buf = io.BytesIO()
        result.save(buf, format="PNG")
        return buf.getvalue()
    except ImportError:
        # realesrgan not installed – fall back to lanczos
        return _upscale_lanczos(image_bytes, scale=4)


def run(image_bytes: bytes, model_key: str = "Lanczos 4x (Fast, No AI)") -> bytes:
    if model_key == "Lanczos 2x (Fast, No AI)":
        return _upscale_lanczos(image_bytes, scale=2)
    if model_key == "Lanczos 4x (Fast, No AI)":
        return _upscale_lanczos(image_bytes, scale=4)
    # Real-ESRGAN
    return _upscale_real_esrgan(image_bytes)
