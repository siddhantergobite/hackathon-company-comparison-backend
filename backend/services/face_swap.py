"""
Face Swap — Landmark-Aligned with Color Correction
====================================================
Pipeline:
  1. InsightFace detects face + 5 landmarks (eyes, nose, mouth) in both images
  2. cv2.estimateAffinePartial2D aligns source face to target landmarks (similarity transform)
  3. Color histogram matching (LAB space) corrects skin tone / lighting difference
  4. cv2.seamlessClone (Poisson blending) merges seamlessly — no hard edges
  5. Optional: feather the clone boundary for extra smoothness

This eliminates the dark shadow artifact from the previous implementation
which used a manual alpha-blend without landmark alignment or color correction.
"""
import io
import cv2
import numpy as np
from PIL import Image

MODELS = {
    "Landmark Aligned + Color Match (Best)": "landmark",
    "Direct Paste (Debug/Fast)":             "direct",
}


def _pil_to_bgr(image_bytes: bytes) -> np.ndarray:
    pil = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    arr = np.array(pil)
    return cv2.cvtColor(arr, cv2.COLOR_RGB2BGR)


def _bgr_to_png(img: np.ndarray) -> bytes:
    buf = io.BytesIO()
    Image.fromarray(cv2.cvtColor(img, cv2.COLOR_BGR2RGB)).save(buf, format="PNG")
    return buf.getvalue()


def _detect_face(bgr_img: np.ndarray):
    """
    Returns (bbox, kps) where:
      bbox = (x1, y1, x2, y2)
      kps  = np.array of 5 key-points [[x,y],...] (left eye, right eye, nose, mouth-L, mouth-R)
    """
    import insightface
    app = insightface.app.FaceAnalysis(
        name="buffalo_sc",
        providers=["CPUExecutionProvider"],
        allowed_modules=["detection"],
    )
    app.prepare(ctx_id=0, det_size=(640, 640))
    rgb = cv2.cvtColor(bgr_img, cv2.COLOR_BGR2RGB)
    faces = app.get(rgb)
    if not faces:
        return None, None
    # Pick the largest face
    best = sorted(
        faces,
        key=lambda f: (f.bbox[2] - f.bbox[0]) * (f.bbox[3] - f.bbox[1]),
        reverse=True
    )[0]
    x1, y1, x2, y2 = [int(v) for v in best.bbox]
    h, w = bgr_img.shape[:2]
    bbox = (max(0, x1), max(0, y1), min(w, x2), min(h, y2))
    kps  = best.kps.astype(np.float32)   # shape (5, 2)
    return bbox, kps


def _match_color(src: np.ndarray, ref: np.ndarray) -> np.ndarray:
    """
    Transfer LAB color statistics from ref (target face region) to src (source face).
    Corrects lighting and skin tone differences — eliminates the dark-shadow artifact.
    """
    src_lab = cv2.cvtColor(src, cv2.COLOR_BGR2LAB).astype(np.float32)
    ref_lab = cv2.cvtColor(ref, cv2.COLOR_BGR2LAB).astype(np.float32)

    for ch in range(3):
        s_mean, s_std = src_lab[:, :, ch].mean(), src_lab[:, :, ch].std() + 1e-6
        r_mean, r_std = ref_lab[:, :, ch].mean(), ref_lab[:, :, ch].std() + 1e-6
        src_lab[:, :, ch] = (src_lab[:, :, ch] - s_mean) * (r_std / s_std) + r_mean

    src_lab = np.clip(src_lab, 0, 255).astype(np.uint8)
    return cv2.cvtColor(src_lab, cv2.COLOR_LAB2BGR)


def run(source_bytes: bytes, target_bytes: bytes,
        model_key: str = "Landmark Aligned + Color Match (Best)") -> bytes:

    src_bgr = _pil_to_bgr(source_bytes)
    tgt_bgr = _pil_to_bgr(target_bytes)

    src_bbox, src_kps = _detect_face(src_bgr)
    tgt_bbox, tgt_kps = _detect_face(tgt_bgr)

    if src_kps is None:
        raise ValueError("No face detected in source image. Use a clear frontal face photo.")
    if tgt_kps is None:
        raise ValueError("No face detected in target image. Use a clear frontal face photo.")

    tgt_h, tgt_w = tgt_bgr.shape[:2]
    sx1, sy1, sx2, sy2 = src_bbox
    tx1, ty1, tx2, ty2 = tgt_bbox

    # ── Debug/fast mode: direct paste ────────────────────────────────────────
    if model_key == "Direct Paste (Debug/Fast)":
        tw, th = tx2 - tx1, ty2 - ty1
        src_face = src_bgr[sy1:sy2, sx1:sx2]
        src_face = cv2.resize(src_face, (tw, th))
        result = tgt_bgr.copy()
        result[ty1:ty2, tx1:tx2] = src_face
        return _bgr_to_png(result)

    # ── Best mode: landmark-aligned + color match + Poisson clone ────────────

    # 1. Estimate similarity transform: aligns source kps → target kps
    M, _ = cv2.estimateAffinePartial2D(
        src_kps, tgt_kps,
        method=cv2.RANSAC,
        ransacReprojThreshold=5.0,
    )
    if M is None:
        raise RuntimeError("Could not compute face alignment transform.")

    # 2. Warp the full source image into target coordinate space
    src_warped = cv2.warpAffine(src_bgr, M, (tgt_w, tgt_h),
                                flags=cv2.INTER_LINEAR,
                                borderMode=cv2.BORDER_REFLECT)

    # 3. Color-correct the warped source to match target face skin/lighting
    tgt_face_region = tgt_bgr[ty1:ty2, tx1:tx2]
    sw1 = max(0, int(tgt_kps[:, 0].min()) - 10)
    sw2 = min(tgt_w, int(tgt_kps[:, 0].max()) + 10)
    sh1 = max(0, int(tgt_kps[:, 1].min()) - 10)
    sh2 = min(tgt_h, int(tgt_kps[:, 1].max()) + 10)
    warped_face_crop = src_warped[sh1:sh2, sw1:sw2]

    if warped_face_crop.size > 0 and tgt_face_region.size > 0:
        try:
            ref_resized = cv2.resize(tgt_face_region,
                                     (warped_face_crop.shape[1], warped_face_crop.shape[0]))
            corrected_crop = _match_color(warped_face_crop, ref_resized)
            src_warped[sh1:sh2, sw1:sw2] = corrected_crop
        except Exception as e:
            print(f"[FaceSwap] Color correction skipped: {e}")

    # 4. Build convex hull mask around target face landmarks (+ padding)
    padded_kps = []
    face_cx = tgt_kps[:, 0].mean()
    face_cy = tgt_kps[:, 1].mean()
    face_scale = max(tx2 - tx1, ty2 - ty1) * 0.55  # radius

    # Build expanded convex hull including bbox corners
    hull_pts = np.array([
        [tx1 - 5,  ty1 - 5],
        [tx2 + 5,  ty1 - 5],
        [tx2 + 5,  ty2 + 5],
        [tx1 - 5,  ty2 + 5],
    ] + tgt_kps.tolist(), dtype=np.int32)

    hull = cv2.convexHull(hull_pts)

    mask = np.zeros((tgt_h, tgt_w), dtype=np.uint8)
    cv2.fillConvexPoly(mask, hull, 255)

    # Slightly erode to keep edges clean
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
    mask = cv2.erode(mask, kernel, iterations=2)

    # 5. Find centroid for seamlessClone
    M_moments = cv2.moments(mask)
    if M_moments["m00"] == 0:
        cx, cy = (tx1 + tx2) // 2, (ty1 + ty2) // 2
    else:
        cx = int(M_moments["m10"] / M_moments["m00"])
        cy = int(M_moments["m01"] / M_moments["m00"])
    center = (cx, cy)

    # 6. Poisson blending — seamlessly merges face with proper gradient
    try:
        result = cv2.seamlessClone(src_warped, tgt_bgr, mask, center, cv2.NORMAL_CLONE)
        print(f"[FaceSwap] Poisson clone OK, center={center}")
    except Exception as e:
        print(f"[FaceSwap] seamlessClone failed ({e}), using manual blend")
        # Fallback: alpha blend
        mask_f = mask.astype(float)[:, :, None] / 255.0
        mask_f = cv2.GaussianBlur(mask_f.squeeze(), (31, 31), 15)[:, :, None]
        result = (src_warped.astype(float) * mask_f +
                  tgt_bgr.astype(float) * (1.0 - mask_f))
        result = np.clip(result, 0, 255).astype(np.uint8)

    return _bgr_to_png(result)
