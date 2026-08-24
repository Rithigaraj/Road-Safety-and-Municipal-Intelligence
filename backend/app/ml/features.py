"""Patch feature extraction for the trainable tile classifier.

Pure-numpy descriptors: HSV colour histograms, intensity statistics,
gradient/edge measures and texture moments - the classic hand-crafted CV
feature set a Random Forest can learn from.
"""
from __future__ import annotations

import numpy as np

TILE = 128


def rgb_to_hsv(arr: np.ndarray) -> np.ndarray:
    """Vectorised RGB(0..255) -> HSV(h 0..1, s, v) without external deps."""
    r, g, b = arr[..., 0] / 255.0, arr[..., 1] / 255.0, arr[..., 2] / 255.0
    maxc = np.max(arr, axis=-1) / 255.0
    minc = np.min(arr, axis=-1) / 255.0
    delta = maxc - minc
    safe = np.where(delta == 0, 1e-9, delta)

    hr = ((g - b) / safe) % 6
    hg = ((b - r) / safe) + 2
    hb = ((r - g) / safe) + 4
    h = np.where(maxc == r / 255.0, hr, np.where(maxc == g / 255.0, hg, hb)) * 60.0
    h = (h % 360) / 360.0
    s = np.where(maxc == 0, 0, delta / np.where(maxc == 0, 1, maxc))
    v = maxc
    return np.stack([h, s, v], axis=-1)


def gray_gradient(gray: np.ndarray) -> np.ndarray:
    """Simple central-difference gradient magnitude."""
    gx = np.zeros_like(gray, dtype=np.float32)
    gy = np.zeros_like(gray, dtype=np.float32)
    gx[:, 1:-1] = gray[:, 2:] - gray[:, :-2]
    gy[1:-1, :] = gray[2:, :] - gray[:-2, :]
    return np.sqrt(gx ** 2 + gy ** 2)


def extract_features(tile_rgb: np.ndarray) -> np.ndarray:
    """Return the 1-D feature vector describing an HxWx3 uint8 patch."""
    t = tile_rgb.astype(np.float32)
    hsv = rgb_to_hsv(t)
    h, s, v = hsv[..., 0], hsv[..., 1], hsv[..., 2]
    gray = t.mean(axis=-1)

    feats: list[np.ndarray | float] = []

    # colour histograms (normalised)
    h_hist, _ = np.histogram(h, bins=12, range=(0.0, 1.0))
    s_hist, _ = np.histogram(s, bins=8, range=(0.0, 1.0))
    v_hist, _ = np.histogram(v, bins=8, range=(0.0, 1.0))
    feats.extend((h_hist / h_hist.sum()).tolist())
    feats.extend((s_hist / s_hist.sum()).tolist())
    feats.extend((v_hist / v_hist.sum()).tolist())

    # intensity / colour moments
    feats.append(gray.mean() / 255.0)
    feats.append(gray.std() / 255.0)
    feats.extend([t[..., 0].mean() / 255.0, t[..., 1].mean() / 255.0,
                  t[..., 2].mean() / 255.0])
    feats.extend([s.mean(), s.std()])
    blue_minus_red = (t[..., 2] - t[..., 0]).mean() / 255.0   # water signature
    green_dominance = (t[..., 1] - np.maximum(t[..., 0], t[..., 2])).mean() / 255.0  # sign vegetation
    feats.extend([blue_minus_red, green_dominance])

    # edges & texture
    grad = gray_gradient(gray)
    feats.extend([grad.mean() / 32.0, grad.std() / 32.0])
    feats.append(float((grad > 24).mean()))                    # edge density
    feats.append(float((gray < 88).mean()))                    # dark fraction
    feats.append(float((gray > 200).mean()))                   # bright fraction

    # coarse quadrant darkness layout (where is the dark mass?)
    qs = [gray[:64, :64], gray[:64, 64:], gray[64:, :64], gray[64:, 64:]]
    qm = np.array([q.mean() for q in qs])
    feats.extend(((qm - qm.mean()) / 255.0).tolist())

    vec = np.array([float(f) for f in feats], dtype=np.float32)
    return np.nan_to_num(vec, nan=0.0, posinf=0.0, neginf=0.0)


FEATURE_SIZE = len(extract_features(np.zeros((TILE, TILE, 3), dtype=np.uint8)))
