"""
Video Clips: trim, text overlay, merge, extract GIF — using moviepy 2.x (free, local).
"""
import io
import os
import tempfile

OPERATIONS = {
    "Trim Video": "trim",
    "Add Text Overlay": "text_overlay",
    "Extract Frames as GIF": "extract_gif",
}


def _tmp(suffix: str) -> str:
    f = tempfile.NamedTemporaryFile(suffix=suffix, delete=False)
    f.close()
    return f.name


def trim_video(video_bytes: bytes, start_sec: float, end_sec: float) -> bytes:
    from moviepy import VideoFileClip

    in_path = _tmp(".mp4")
    out_path = _tmp(".mp4")
    try:
        with open(in_path, "wb") as f:
            f.write(video_bytes)
        clip = VideoFileClip(in_path).subclipped(start_sec, end_sec)
        clip.write_videofile(out_path, codec="libx264", audio_codec="aac",
                             verbose=False, logger=None)
        clip.close()
        with open(out_path, "rb") as f:
            return f.read()
    finally:
        for p in [in_path, out_path]:
            try:
                os.unlink(p)
            except Exception:
                pass


def add_text_overlay(video_bytes: bytes, text: str, font_size: int = 40) -> bytes:
    from moviepy import VideoFileClip, TextClip, CompositeVideoClip

    in_path = _tmp(".mp4")
    out_path = _tmp(".mp4")
    try:
        with open(in_path, "wb") as f:
            f.write(video_bytes)
        clip = VideoFileClip(in_path)
        txt = (TextClip(font="Arial", text=text, font_size=font_size, color="white")
               .with_position("center")
               .with_duration(clip.duration))
        composite = CompositeVideoClip([clip, txt])
        composite.write_videofile(out_path, codec="libx264", verbose=False, logger=None)
        composite.close()
        with open(out_path, "rb") as f:
            return f.read()
    finally:
        for p in [in_path, out_path]:
            try:
                os.unlink(p)
            except Exception:
                pass


def extract_gif(video_bytes: bytes, fps: int = 5, max_duration: float = 5.0) -> bytes:
    from moviepy import VideoFileClip

    in_path = _tmp(".mp4")
    out_path = _tmp(".gif")
    try:
        with open(in_path, "wb") as f:
            f.write(video_bytes)
        clip = VideoFileClip(in_path)
        clip = clip.subclipped(0, min(clip.duration, max_duration))
        clip.write_gif(out_path, fps=fps, verbose=False, logger=None)
        clip.close()
        with open(out_path, "rb") as f:
            return f.read()
    finally:
        for p in [in_path, out_path]:
            try:
                os.unlink(p)
            except Exception:
                pass


def run(video_bytes: bytes, operation: str, **kwargs) -> bytes:
    op = OPERATIONS.get(operation, operation)
    if op == "trim":
        return trim_video(video_bytes,
                          float(kwargs.get("start_sec", 0)),
                          float(kwargs.get("end_sec", 10)))
    if op == "text_overlay":
        return add_text_overlay(video_bytes, kwargs.get("text", "Hello World"))
    if op == "extract_gif":
        return extract_gif(video_bytes, int(kwargs.get("fps", 5)))
    raise ValueError(f"Unknown operation: {operation}")
