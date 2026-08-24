"""Severity model: turns a visual detection into a severity grade.

The score fuses detection confidence with visual evidence (contrast, size,
density) and class-specific escalation rules.
"""
from __future__ import annotations

from dataclasses import dataclass

from .classes import SEVERITY_ORDER
from .detector import Detection


@dataclass
class SeverityResult:
    label: str  # low | medium | high | critical
    score: float  # 0..1
    reason: str
    size_estimate_cm: float | None = None


# Camera assumptions used to convert pixel sizes into approximate real-world
# centimetres. A phone/CCTV frame at ~4 m with a ~63 degree horizontal FOV.
ASSUMED_DISTANCE_M = 4.0
ASSUMED_HFOV_DEG = 63.0

# Extra escalation for classes that are already dangerous by nature.
CLASS_ESCALATION = {
    "pothole": 0.08,
    "water_leakage": 0.05,
    "blocked_drainage": 0.04,
    "damaged_traffic_sign": 0.06,
    "road_crack": 0.02,
    "garbage": 0.0,
    "broken_streetlight": 0.0,
}


def _grade(score: float) -> str:
    if score >= 0.75:
        return "critical"
    if score >= 0.55:
        return "high"
    if score >= 0.32:
        return "medium"
    return "low"


def estimate_size_cm(detection) -> float | None:
    """Approximate the real-world width of the detected region in centimetres."""
    import math

    frame = getattr(detection, "frame_size", None)
    if not frame or frame[0] <= 0:
        return None
    x1, y1, x2, y2 = detection.bbox
    w_px = max(x2 - x1, 1)
    frame_w = frame[0]
    view_width_m = 2.0 * ASSUMED_DISTANCE_M * math.tan(math.radians(ASSUMED_HFOV_DEG) / 2)
    return round(view_width_m * (w_px / frame_w) * 100.0, 1)


def compute_severity(detection: Detection) -> SeverityResult:
    conf = detection.confidence
    ev = detection.evidence
    x1, y1, x2, y2 = detection.bbox
    w, h = max(x2 - x1, 1), max(y2 - y1, 1)
    size_ratio = min(1.0, (w * h) / (256.0 * 256.0))

    # pull class-specific visual signals out of the evidence dict
    contrast = float(ev.get("contrast", 0.0))
    density = float(ev.get("debris_density", ev.get("compactness", 0.0)))
    elongation = float(ev.get("elongation", 0.0))
    dark_frac = float(ev.get("dark_frac", 0.0))

    base = 0.35 * conf + 0.25 * size_ratio
    if contrast:
        base += 0.3 * min(1.0, contrast * 1.5)
    if density:
        base += 0.2 * min(1.0, density * 2.0)
    if dark_frac:
        base += 0.2 * min(1.0, dark_frac * 3.0)
    if elongation:
        base += 0.05 * min(1.0, elongation / 5.0)

    base += CLASS_ESCALATION.get(detection.class_name, 0.0)

    # large physical defects escalate one notch
    size_cm = estimate_size_cm(detection)
    if size_cm is not None and size_cm > 90:
        base += 0.06

    score = min(1.0, max(0.0, base))

    label = _grade(score)
    reason = (f"confidence {conf:.2f}, visual severity signals "
              f"contrast={contrast:.2f}, density={density:.2f}, size={size_ratio:.2f}")
    if size_cm is not None:
        reason += f", approx width {size_cm:.0f}cm"
    return SeverityResult(label=label, score=round(score, 3), reason=reason,
                          size_estimate_cm=size_cm)


def severity_rank(label: str) -> int:
    return SEVERITY_ORDER[label]
