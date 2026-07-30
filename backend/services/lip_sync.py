"""
Lip Sync Service
=================
Uses HuggingFace Spaces via gradio_client — no local setup required.

Priority:
  1. LatentSync (fffiloni/LatentSync) — state-of-the-art, free HF Space
  2. SadTalker  (vinthony/SadTalker)  — audio-driven talking head, free HF Space
  3. Audio Replace fallback            — replaces video audio with new audio via moviepy
                                         (not true lip sync but fully functional)
"""
import io
import os
import tempfile

MODELS = {
    "LatentSync (Best — HF Space)": "latentsync",
    "SadTalker  (Talking Head)":    "sadtalker",
    "Audio Replace (Fast Fallback)": "audio_replace",
}


def _save_temp(data: bytes, suffix: str) -> str:
    f = tempfile.NamedTemporaryFile(suffix=suffix, delete=False)
    f.write(data)
    f.close()
    return f.name


def _cleanup(*paths):
    for p in paths:
        try:
            os.unlink(p)
        except Exception:
            pass


def _latentsync(video_path: str, audio_path: str) -> bytes:
    """LatentSync via HuggingFace Space — best quality lip sync, free."""
    from gradio_client import Client, handle_file

    print("[LipSync] Trying LatentSync HF Space...")
    client = Client("fffiloni/LatentSync")

    result = client.predict(
        video=handle_file(video_path),
        audio=handle_file(audio_path),
        api_name="/predict",
    )

    # result is a filepath
    result_path = result if isinstance(result, str) else result[0]
    with open(result_path, "rb") as f:
        data = f.read()
    print(f"[LipSync] LatentSync OK -> {len(data)} bytes")
    return data


def _sadtalker(video_path: str, audio_path: str) -> bytes:
    """SadTalker via HuggingFace Space — talking head animation."""
    from gradio_client import Client, handle_file

    print("[LipSync] Trying SadTalker HF Space...")
    client = Client("vinthony/SadTalker")

    result = client.predict(
        source_image=handle_file(video_path),  # SadTalker takes an image + audio
        driven_audio=handle_file(audio_path),
        preprocess="crop",
        still_mode=False,
        use_enhancer=False,
        batch_size=1,
        size=256,
        pose_style=0,
        exp_scale=1.0,
        api_name="/test",
    )

    result_path = result if isinstance(result, str) else result[0]
    with open(result_path, "rb") as f:
        data = f.read()
    print(f"[LipSync] SadTalker OK -> {len(data)} bytes")
    return data


def _audio_replace(video_path: str, audio_path: str) -> bytes:
    """
    Fallback: replace the video's audio track with the new audio.
    Not true lip sync but produces a valid video with the new voice.
    """
    from moviepy import VideoFileClip, AudioFileClip

    out_path = _save_temp(b"", ".mp4")
    try:
        video = VideoFileClip(video_path)
        audio = AudioFileClip(audio_path)

        # Trim audio to video length if needed
        if audio.duration > video.duration:
            audio = audio.subclipped(0, video.duration)

        result = video.with_audio(audio)
        result.write_videofile(out_path, codec="libx264", audio_codec="aac",
                               verbose=False, logger=None)
        video.close()
        audio.close()
        result.close()

        with open(out_path, "rb") as f:
            data = f.read()
        print(f"[LipSync] Audio replace OK -> {len(data)} bytes")
        return data
    finally:
        _cleanup(out_path)


def run(video_bytes: bytes, audio_bytes: bytes,
        model_key: str = "LatentSync (Best — HF Space)") -> bytes:

    video_path = _save_temp(video_bytes, ".mp4")
    audio_path = _save_temp(audio_bytes, ".wav")

    try:
        model_val = MODELS.get(model_key, "latentsync")

        if model_val == "latentsync":
            try:
                return _latentsync(video_path, audio_path)
            except Exception as e:
                print(f"[LipSync] LatentSync failed ({e}), trying SadTalker...")
                try:
                    return _sadtalker(video_path, audio_path)
                except Exception as e2:
                    print(f"[LipSync] SadTalker failed ({e2}), using audio replace...")
                    return _audio_replace(video_path, audio_path)

        elif model_val == "sadtalker":
            try:
                return _sadtalker(video_path, audio_path)
            except Exception as e:
                print(f"[LipSync] SadTalker failed ({e}), using audio replace...")
                return _audio_replace(video_path, audio_path)

        else:
            return _audio_replace(video_path, audio_path)

    finally:
        _cleanup(video_path, audio_path)
