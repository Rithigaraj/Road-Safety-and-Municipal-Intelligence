"""Detection backends.

Primary backend: a self-contained heuristic detector (pure numpy/PIL) so the
system runs out of the box with no model downloads.

Optional backend: Ultralytics YOLO, activated by setting DETECTOR_BACKEND=yolo
or auto (falls back to heuristic when ultralytics is not installed).
"""
from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass, field

import numpy as np
from PIL import Image

from ..config import CONFIDENCE_THRESHOLD
from .classes import PROBLEM_CLASSES


@dataclass
class Detection:
    class_name: str
    confidence: float
    bbox: tuple[int, int, int, int]  # (x1, y1, x2, y2) in original-image pixels
    evidence: dict = field(default_factory=dict)
    frame_size: tuple[int, int] | None = None  # (width, height) of source image


# ---------------------------------------------------------------- utilities

def _to_gray(arr: np.ndarray) -> np.ndarray:
    r, g, b = arr[..., 0], arr[..., 1], arr[..., 2]
    return (0.299 * r + 0.587 * g + 0.114 * b).astype(np.float32)


def _connected_components(mask: np.ndarray):
    """Label 4-connected components. Returns list of dicts with features."""
    h, w = mask.shape
    labels = np.zeros((h, w), dtype=np.int32)
    current = 0
    comps = {}
    # BFS with flat arrays
    flat = mask.reshape(-1)
    visited = np.zeros(h * w, dtype=bool)
    neighbors = [(-1, 0), (1, 0), (0, -1), (0, 1)]
    for idx in range(h * w):
        if flat[idx] and not visited[idx]:
            current += 1
            ys, xs = [], []
            queue = deque([idx])
            visited[idx] = True
            while queue:
                p = queue.popleft()
                y, x = divmod(p, w)
                ys.append(y)
                xs.append(x)
                for dy, dx in neighbors:
                    ny, nx = y + dy, x + dx
                    if 0 <= ny < h and 0 <= nx < w:
                        nidx = ny * w + nx
                        if flat[nidx] and not visited[nidx]:
                            visited[nidx] = True
                            queue.append(nidx)
            ys, xs = np.array(ys), np.array(xs)
            comps[current] = {
                "pixels": len(ys),
                "y_min": int(ys.min()), "y_max": int(ys.max()),
                "x_min": int(xs.min()), "x_max": int(xs.max()),
                "ys": ys, "xs": xs,
            }
            for yy, xx in zip(ys, xs):
                labels[yy, xx] = current
    return comps, labels


def _elongation(ys: np.ndarray, xs: np.ndarray) -> float:
    if len(ys) < 4:
        return 1.0
    cov = np.cov(np.stack([ys, xs]))
    try:
        eig = np.linalg.eigvalsh(cov)
    except np.linalg.LinAlgError:
        return 1.0
    small = max(eig[0], 1e-6)
    return float(eig[1] / small)


def _saturate(v: float) -> float:
    return max(0.0, min(1.0, float(v)))


class HeuristicDetector:
    """Self-contained computer-vision-lite detector.

    Uses simple, explainable heuristics (dark blobs, saturation clusters,
    colour masks, elongation) tuned to the seven infrastructure problem
    classes. Good enough to power the demo pipeline on synthetic and
    clearly-photographed real images; swap in a YOLO backend for production.
    """

    name = "heuristic"
    max_dim = 256  # working resolution

    def __init__(self, confidence_threshold: float = CONFIDENCE_THRESHOLD):
        self.confidence_threshold = confidence_threshold

    # -- core entry ---------------------------------------------------------
    def detect(self, image: Image.Image) -> list[Detection]:
        arr = self._load(image)
        detections: list[Detection] = []
        detections += self._detect_dark_road_flaws(arr)
        detections += self._detect_garbage(arr)
        detections += self._detect_water_leakage(arr)
        detections += self._detect_streetlight(arr)
        detections += self._detect_traffic_sign(arr)
        detections += self._detect_blocked_drainage(arr)

        kept = []
        for d in detections:
            if d.confidence >= self.confidence_threshold:
                d.frame_size = image.size
                kept.append(d)
        kept.sort(key=lambda d: d.confidence, reverse=True)
        return kept

    # -- helpers ------------------------------------------------------------
    def _load(self, image: Image.Image) -> np.ndarray:
        rgb = image.convert("RGB")
        rgb.thumbnail((self.max_dim, self.max_dim))
        return np.asarray(rgb).astype(np.float32)

    @staticmethod
    def _scale_bbox(bbox, arr_shape, orig_size) -> tuple[int, int, int, int]:
        sy = orig_size[1] / arr_shape[0]
        sx = orig_size[0] / arr_shape[1]
        x1, y1, x2, y2 = bbox
        return (int(x1 * sx), int(y1 * sy), int(x2 * sx), int(y2 * sy))

    # -- heuristics ---------------------------------------------------------
    def _detect_dark_road_flaws(self, arr) -> list[Detection]:
        """Potholes (blob-like dark regions) and cracks (elongated dark lines)."""
        gray = _to_gray(arr)
        mean, std = float(gray.mean()), float(gray.std())
        # low-contrast night scenes are handled by the streetlight detector;
        # potholes/cracks cannot be read reliably on an unlit road.
        if mean < 0.40 * 255 and std < 22:
            return []
        dark = gray < max(mean - 0.9 * std, mean * 0.72)
        comps, _ = self._connected(dark)
        dets: list[Detection] = []
        h, w = gray.shape
        area_ratio = lambda c: c["pixels"] / (h * w)
        for c in comps.values():
            if c["pixels"] < 0.0006 * h * w or c["pixels"] > 0.35 * h * w:
                continue
            bw, bh = c["x_max"] - c["x_min"] + 1, c["y_max"] - c["y_min"] + 1
            compactness = c["pixels"] / max(bw * bh, 1)
            elong = _elongation(c["ys"], c["xs"])
            ys, xs = c["ys"], c["xs"]
            # skip strongly blue-dominant dark regions -> likely water, not asphalt flaws
            b_chan, r_chan, g_chan = arr[..., 2], arr[..., 0], arr[..., 1]
            blue_dominance = float((b_chan[ys, xs] - np.maximum(r_chan[ys, xs], g_chan[ys, xs])).mean())
            if blue_dominance > 15:
                continue
            dark_mean = float(gray[ys, xs].mean())
            contrast = _saturate((mean - dark_mean) / max(mean, 1.0))
            bbox = (c["x_min"], c["y_min"], c["x_max"], c["y_max"])

            if elong > 2.6 and compactness < 0.55:
                # thin winding line -> road crack
                coverage = (c["y_max"] - c["y_min"]) / h
                conf = _saturate(0.4 * contrast * 3.0 + 0.2 * coverage + 0.1 * compactness)
                dets.append(Detection("road_crack", conf, bbox,
                                      {"contrast": round(contrast, 3), "elongation": round(elong, 2)}))
            elif compactness >= 0.42 and elong < 2.6 and 0.02 * h * w <= c["pixels"] <= 0.25 * h * w:
                # dense dark blob -> pothole
                conf = _saturate(0.4 * contrast * 3.0 + 0.25 * compactness + 0.2 * area_ratio(c) * 8)
                dets.append(Detection("pothole", conf, bbox,
                                      {"contrast": round(contrast, 3), "compactness": round(compactness, 2)}))
        return dets

    def _detect_garbage(self, arr) -> list[Detection]:
        """Garbage: dense clusters of high-saturation, multi-hue pixels."""
        hsv = self._hsv(arr)
        sat = hsv[..., 1]
        hue = hsv[..., 0]
        vivid = sat > 0.45
        comps, _ = self._connected(vivid)
        h, w = sat.shape
        dets: list[Detection] = []
        for c in comps.values():
            if c["pixels"] < 0.002 * h * w or c["pixels"] > 0.5 * h * w:
                continue
            hues = hue[c["ys"], c["xs"]]
            hue_span = float(hues.max() - hues.min()) if len(hues) > 1 else 0.0
            mean_sat = float(sat[c["ys"], c["xs"]].mean())
            bw, bh = c["x_max"] - c["x_min"] + 1, c["y_max"] - c["y_min"] + 1
            compactness = c["pixels"] / max(bw * bh, 1)
            diversity = _saturate(hue_span / 0.5)
            conf = _saturate(0.4 * mean_sat * 2.0 + 0.25 * diversity + 0.25 * compactness)
            if conf >= self.confidence_threshold:
                dets.append(Detection("garbage", conf,
                                      (c["x_min"], c["y_min"], c["x_max"], c["y_max"]),
                                      {"hue_span": round(hue_span, 2), "mean_sat": round(mean_sat, 2)}))
        return dets

    def _detect_water_leakage(self, arr) -> list[Detection]:
        """Water leakage: dark glossy blue-ish puddle on a road surface."""
        r, g, b = arr[..., 0], arr[..., 1], arr[..., 2]
        blueish = (b > r + 25) & (b > g + 20) & (b > 70)
        dark = (_to_gray(arr) < 0.60 * 255)
        glossy = dark & blueish
        comps, _ = self._connected(glossy)
        h, w = arr.shape[:2]
        dets: list[Detection] = []
        for c in comps.values():
            if c["pixels"] < 0.004 * h * w:
                continue
            blue_strength = float((b[c["ys"], c["xs"]] - r[c["ys"], c["xs"]]).mean())
            bw, bh = c["x_max"] - c["x_min"] + 1, c["y_max"] - c["y_min"] + 1
            compactness = c["pixels"] / max(bw * bh, 1)
            spread = c["pixels"] / (h * w)
            conf = _saturate(0.35 * blue_strength / 50.0 + 0.3 * compactness + 0.35 * spread * 12)
            if conf >= self.confidence_threshold:
                dets.append(Detection("water_leakage", conf,
                                      (c["x_min"], c["y_min"], c["x_max"], c["y_max"]),
                                      {"blue_strength": round(blue_strength, 1)}))
        return dets

    def _detect_streetlight(self, arr) -> list[Detection]:
        """Broken streetlight: night scene with a pole but no glowing lamp."""
        gray = _to_gray(arr)
        h, w = gray.shape
        if float(gray.mean()) > 0.50 * 255:  # daylight scene
            return []
        # a broken pole: narrow, tall, solid-dark column in the lower half
        lower = gray[h // 2:, :]
        base, sd = float(lower.mean()), float(lower.std())
        if sd < 3.0:
            return []
        dark_col = (lower < base - 0.6 * sd).sum(axis=0) / (h // 2)
        cols = np.where(dark_col > 0.6)[0]
        if len(cols) == 0:
            return []
        pole_groups = np.split(cols, np.where(np.diff(cols) > 6)[0] + 1)
        pole = max(pole_groups, key=len)
        pole_width = int(pole.max() - pole.min()) + 1
        if not (0.01 * w <= pole_width <= 0.16 * w):
            return []
        bright = gray > float(gray.mean()) + 1.5 * float(gray.std())
        glow_area = float(bright.sum()) / (h * w)
        if glow_area > 0.02:  # a lamp is visibly glowing
            return []
        x1, x2 = int(pole.min()), int(pole.max())
        y1, y2 = h // 2, h - 1
        conf = _saturate(0.55 + 0.2 * (1.0 - glow_area * 50) + 0.1 * (pole_width / max(w * 0.1, 1)))
        return [Detection("broken_streetlight", conf, (x1, y1, x2, y2),
                          {"night_darkness": round(float(gray.mean()) / 255, 2),
                           "glow_area": round(glow_area, 4)})]

    def _detect_traffic_sign(self, arr) -> list[Detection]:
        """Damaged traffic sign: sign-coloured panel with a dark defect inside it."""
        hsv = self._hsv(arr)
        hue = hsv[..., 0]
        sat = hsv[..., 1]
        r, g, b = arr[..., 0], arr[..., 1], arr[..., 2]
        # signs are usually blue (0.5-0.75), green (0.22-0.45) or red (~0.0)
        blue_sign = (sat > 0.3) & ((hue > 0.5) & (hue < 0.75))
        green_sign = (sat > 0.3) & ((hue > 0.22) & (hue < 0.45))
        red_sign = (sat > 0.35) & ((hue < 0.05) | (hue > 0.95))
        sign_mask = blue_sign | green_sign | red_sign
        comps, _ = self._connected(sign_mask)
        gray = _to_gray(arr)
        dets: list[Detection] = []
        h, w = gray.shape
        for c in comps.values():
            if c["pixels"] < 0.006 * h * w:
                continue
            bw, bh = c["x_max"] - c["x_min"] + 1, c["y_max"] - c["y_min"] + 1
            if bw / max(bh, 1) < 1.3 and bh / max(bw, 1) < 1.3:
                continue  # panels are noticeably wider or taller than they are square
            area_frac = c["pixels"] / (h * w)
            if area_frac > 0.35 or (bw / max(bh, 1)) > 6 or (bh / max(bw, 1)) > 6:
                continue
            # signs are single-colour; refuse multi-hue clusters (garbage piles)
            comp_hues = hue[c["ys"], c["xs"]]
            hue_std = float(comp_hues.std()) if len(comp_hues) > 1 else 1.0
            if hue_std > 0.06:
                continue
            # strongly blue-dominant panels are almost always pooled water
            blue_dominance = float((b[c["ys"], c["xs"]] - np.maximum(r[c["ys"], c["xs"]], g[c["ys"], c["xs"]])).mean())
            if blue_dominance > 25:
                continue
            x1, y1, x2, y2 = c["x_min"], c["y_min"], c["x_max"], c["y_max"]
            region = gray[y1:y2 + 1, x1:x2 + 1]
            dark_frac = float((region < float(region.mean()) - 0.8 * float(region.std())).mean())
            panel_solidity = c["pixels"] / max(bw * bh, 1)
            conf = _saturate(0.45 + 0.45 * dark_frac * 4.0 + 0.1 * panel_solidity)
            if dark_frac > 0.12 and conf >= self.confidence_threshold:
                dets.append(Detection("damaged_traffic_sign", conf,
                                      (x1, y1, x2, y2),
                                      {"dark_frac": round(dark_frac, 3), "solidity": round(panel_solidity, 2)}))
        return dets

    def _detect_blocked_drainage(self, arr) -> list[Detection]:
        """Blocked drainage: a grille (dark horizontal bars) covered by a debris pile."""
        gray = _to_gray(arr)
        h, w = gray.shape
        if float(gray.mean()) < 0.40 * 255:  # requires a daylight road scene
            return []
        # grille: horizontal band of *striped* rows (several dark bars with gaps) in the bottom third
        band = gray[int(h * 0.6):, :]
        dark_band = band < float(band.mean()) - 0.5 * float(band.std())
        row_dark = dark_band.sum(axis=1) / w

        def _bar_runs(row_mask: np.ndarray) -> int:
            if not row_mask.any():
                return 0
            edges = np.diff(row_mask.astype(np.int8))
            return int((edges == 1).sum() + (1 if row_mask[0] else 0))

        runs_per_row = np.array([_bar_runs(dark_band[i]) for i in range(dark_band.shape[0])])
        # grate rows alternate dark bars with light gaps -> several runs; solid
        # debris or a single pothole produce only 1-2 runs.
        rows = np.where((row_dark > 0.15) & (row_dark < 0.85) & (runs_per_row >= 3))[0]
        if len(rows) < 2:
            return []
        y1 = int(h * 0.6) + int(rows.min())
        y2 = int(h * 0.6) + int(rows.max())
        grille_height = (y2 - y1) / h
        if not (0.04 <= grille_height <= 0.45):
            return []
        # a real road grate spans most of the road width
        dark_cols = np.where(dark_band.sum(axis=0) > 0.2 * (len(rows)))[0]
        if len(dark_cols) == 0 or (dark_cols.max() - dark_cols.min() + 1) < 0.6 * w:
            return []
        # debris: high-density dark mass sitting on top of the grille
        debris_region = gray[max(0, y1 - 40):y1 + 1, :]
        debris_dark = debris_region < float(gray.mean()) - 0.7 * float(gray.std())
        density = float(debris_dark.mean())
        gap_rows = ((dark_band.sum(axis=1) < 0.7 * w) & (dark_band.sum(axis=1) > 0.1 * w)).sum()
        grille_style = 1.0 if gap_rows > 0 else 0.4
        conf = _saturate(0.35 + 0.4 * density * 2.5 + 0.15 * grille_style + 0.1 * grille_height)
        if conf >= self.confidence_threshold and density > 0.15:
            return [Detection("blocked_drainage", conf, (0, y1, w, y2),
                              {"debris_density": round(density, 3), "grille_style": round(grille_style, 2)})]
        return []

    def _connected(self, mask: np.ndarray):
        return _connected_components(mask)

    @staticmethod
    def _hsv(arr: np.ndarray) -> np.ndarray:
        from colorsys import rgb_to_hsv
        r, g, b = arr[..., 0], arr[..., 1], arr[..., 2]
        r, g, b = r / 255.0, g / 255.0, b / 255.0
        maxc = np.maximum(np.maximum(r, g), b)
        minc = np.minimum(np.minimum(r, g), b)
        delta = maxc - minc
        h = np.zeros_like(maxc)
        d = delta.copy()
        d[d == 0] = 1e-9
        mask = maxc == r
        h[mask] = (60 * (((g - b) / d) % 6))[mask]
        mask = (maxc == g) & (maxc != r)
        h[mask] = (60 * (((b - r) / d) + 2))[mask]
        mask = (maxc == b) & (maxc != r) & (maxc != g)
        h[mask] = (60 * (((r - g) / d) + 4))[mask]
        h = (h + 360) % 360
        s = np.where(maxc != 0, delta / maxc, 0)
        v = maxc
        return np.stack([h / 360.0, s, v], axis=-1)


class YoloDetector:
    """Ultralytics YOLO backend (optional, requires `ultralytics` + weights)."""

    name = "yolo"

    def __init__(self, model_path: str, confidence_threshold: float = CONFIDENCE_THRESHOLD):
        from ultralytics import YOLO  # imported lazily
        self.model = YOLO(model_path)
        self.confidence_threshold = confidence_threshold

    def detect(self, image: Image.Image) -> list[Detection]:
        results = self.model.predict(np.asarray(image.convert("RGB")), conf=self.confidence_threshold, verbose=False)
        dets: list[Detection] = []
        for r in results:
            for box in r.boxes:
                name = r.names[int(box.cls)]
                mapped = name if name in PROBLEM_CLASSES else None
                if mapped is None:
                    continue
                conf = float(box.conf)
                x1, y1, x2, y2 = (int(v) for v in box.xyxy[0].tolist())
                dets.append(Detection(mapped, conf, (x1, y1, x2, y2),
                                      {"yolo_name": name}, frame_size=image.size))
        dets.sort(key=lambda d: d.confidence, reverse=True)
        return dets


def get_detector(backend: str = "auto", model_path: str = ""):
    """Factory.

    auto    -> yolo if installed, else sklearn RF model if trained, else heuristic
    yolo    -> ultralytics YOLO (must be installed)
    sklearn -> trained RandomForest tile classifier (run scripts/train_classifier)
    heuristic -> built-in rule-based CV
    """
    import os

    requested = os.getenv("DETECTOR_BACKEND", backend or "heuristic")
    if requested in ("yolo", "auto"):
        try:
            from .classes import DETECTABLE_CLASSES  # noqa: F401
            from ultralytics import YOLO  # noqa: F401
            return YoloDetector(model_path or os.getenv("YOLO_MODEL_PATH", "yolov8n.pt"))
        except Exception:
            if requested == "yolo":
                raise
    if requested in ("sklearn", "auto"):
        try:
            from .ml_detector import SklearnDetector
            return SklearnDetector()
        except FileNotFoundError:
            if requested == "sklearn":
                raise
    return HeuristicDetector()
