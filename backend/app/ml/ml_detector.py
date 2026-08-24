"""Scikit-learn detection backend: a Random Forest tile classifier.

The image is scanned with a sliding 128px window; each tile is described by
hand-crafted features (see features.py) and classified into one of the seven
problem classes or 'background'. Adjacent same-class tiles are merged into
bounding boxes via connected components - a miniature RPN, in effect.

Train it with:  python -m scripts.train_classifier
"""
from __future__ import annotations

import os
from pathlib import Path

import numpy as np
from PIL import Image

from .classes import DETECTABLE_CLASSES
from .features import TILE, extract_features
from .detector import Detection

MODEL_PATH = Path(
    os.getenv(
        "TILE_MODEL_PATH",
        Path(__file__).resolve().parent.parent.parent / "data" / "models" / "tile_rf.joblib",
    )
)

STRIDE = 64          # sliding-window step (overlap = TILE - STRIDE)
MIN_TILES = 1        # minimum merged tiles to accept a component


def _load_model():
    import joblib

    if not MODEL_PATH.exists():
        raise FileNotFoundError(f"model not trained yet: {MODEL_PATH}")
    return joblib.load(MODEL_PATH)


def _connected(mask: np.ndarray) -> list[list[tuple[int, int]]]:
    """4-connected components over a boolean grid -> list of cell lists."""
    seen = np.zeros_like(mask, dtype=bool)
    comps = []
    h, w = mask.shape
    for y in range(h):
        for x in range(w):
            if not mask[y, x] or seen[y, x]:
                continue
            stack, cells = [(y, x)], []
            seen[y, x] = True
            while stack:
                cy, cx = stack.pop()
                cells.append((cy, cx))
                for ny, nx in ((cy - 1, cx), (cy + 1, cx), (cy, cx - 1), (cy, cx + 1)):
                    if 0 <= ny < h and 0 <= nx < w and mask[ny, nx] and not seen[ny, nx]:
                        seen[ny, nx] = True
                        stack.append((ny, nx))
            comps.append(cells)
    return comps


class SklearnDetector:
    """Trained RandomForest detector. Same interface as the other backends."""

    name = "sklearn"

    def __init__(self, confidence_threshold: float | None = None, bundle=None):
        if bundle is None:
            bundle = _load_model()
        self.model = bundle["model"]
        self.version = bundle.get("version", "?")
        self.confidence_threshold = (
            confidence_threshold
            if confidence_threshold is not None
            else float(os.getenv("CONFIDENCE_THRESHOLD", "0.35"))
        )

    # ------------------------------------------------------------------
    def detect(self, image: Image.Image) -> list[Detection]:
        img = image.convert("RGB")
        arr = np.asarray(img)
        fh, fw = arr.shape[:2]
        frame_size = (fw, fh)

        rows_grid = ((fh - TILE) // STRIDE + 1, (fw - TILE) // STRIDE + 1)
        tiles, coords = [], []
        gy = 0
        while gy * STRIDE + TILE <= fh:
            gx = 0
            while gx * STRIDE + TILE <= fw:
                y, x = gy * STRIDE, gx * STRIDE
                tiles.append(extract_features(arr[y:y + TILE, x:x + TILE]))
                coords.append((gy, gx))
                gx += 1
            gy += 1

        if not tiles:
            return []

        preds = self.model.predict_proba(np.stack(tiles))
        classes = list(self.model.classes_)
        bg_idx = classes.index("background") if "background" in classes else -1

        # each tile votes for exactly one class: its argmax (background wins ties)
        best_idx = np.argmax(preds, axis=1)
        best_prob = preds[np.arange(len(tiles)), best_idx]

        # strong-tile gate: only confident, non-background votes count
        strong_threshold = max(self.confidence_threshold, 0.66)
        keep = (best_idx != bg_idx) & (best_prob >= strong_threshold)

        probs_by_class: dict[str, np.ndarray] = {
            cls: np.zeros(rows_grid) for cls in DETECTABLE_CLASSES
        }
        for (gy_, gx_), k, bi, bp in zip(coords, keep, best_idx, best_prob):
            if not k:
                continue
            cls = classes[bi]
            if cls in probs_by_class and bp > probs_by_class[cls][gy_, gx_]:
                probs_by_class[cls][gy_, gx_] = float(bp)

        detections: list[Detection] = []
        for cls in DETECTABLE_CLASSES:
            mask = probs_by_class[cls] > 0
            if not mask.any():
                continue
            for cells in _connected(mask):
                ps = [probs_by_class[cls][cy, cx] for cy, cx in cells]
                p_max, p_mean = float(max(ps)), float(np.mean(ps))
                conf = round(0.55 * p_max + 0.45 * p_mean, 3)
                if conf < self.confidence_threshold or len(cells) == 1 and p_mean < 0.7:
                    continue
                ys = [c[0] for c in cells]
                xs = [c[1] for c in cells]
                x1 = min(xs) * STRIDE
                y1 = min(ys) * STRIDE
                x2 = (max(xs) + 1) * STRIDE + (TILE - STRIDE)
                y2 = (max(ys) + 1) * STRIDE + (TILE - STRIDE)
                x2, y2 = min(x2, fw), min(y2, fh)
                evidence = self._region_evidence(arr[y1:y2, x1:x2], conf)
                detections.append(Detection(cls, conf, (int(x1), int(y1), int(x2), int(y2)),
                                            evidence, frame_size=frame_size))

        detections.sort(key=lambda d: d.confidence, reverse=True)
        return detections

    # ------------------------------------------------------------------
    @staticmethod
    def _region_evidence(region: np.ndarray, conf: float) -> dict:
        """Real visual stats for the severity model's evidence fusion."""
        if region.size == 0:
            return {"tile_prob": conf}
        t = region.astype(np.float32)
        gray = t.mean(axis=-1)
        from .features import gray_gradient

        grad = gray_gradient(gray)
        dark_frac = float((gray < 88).mean())
        blue_dom = float((t[..., 2] - t[..., 0]).mean() / 255.0)
        contrast = float(gray.std() / 64.0)
        density = float((grad > 24).mean())
        return {
            "contrast": round(min(contrast, 2.0), 3),
            "dark_frac": round(dark_frac, 3),
            "debris_density": round(density, 3),
            "blue_dominance": round(blue_dom, 3),
            "elongation": round(float(max(gray.shape) / max(min(gray.shape), 1)), 2),
            "tile_prob": conf,
        }
