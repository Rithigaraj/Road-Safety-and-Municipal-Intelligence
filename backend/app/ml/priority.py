"""Priority prediction.

priority = class_risk * w1 + severity * w2 + location_importance * w3 + recency * w4
then bucketed into P1..P4 with a suggested SLA.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

from .classes import PROBLEM_CLASSES, SLA_HOURS, priority_level_for_score
from .severity import SeverityResult

W1, W2, W3, W4 = 0.30, 0.38, 0.20, 0.12

CITY_CENTER = (77.5946, 12.9716)  # lat, lon of the demo municipality


def location_importance(lat: float | None, lon: float | None) -> float:
    """High importance near the city core; also model distance to known services."""
    if lat is None or lon is None:
        return 0.5
    # rough degree-distance to city center
    dlat = lat - CITY_CENTER[1]
    dlon = (lon - CITY_CENTER[0]) * abs(math.cos(math.radians(CITY_CENTER[1])))
    dist = (dlat ** 2 + dlon ** 2) ** 0.5
    if dist < 0.03:
        return 1.0   # city core / central business district
    if dist < 0.12:
        return 0.8   # inner ring (schools, hospitals zone)
    if dist < 0.30:
        return 0.6   # residential mid-ring
    return 0.4       # outer ring


def recency_weight(hours_old: float) -> float:
    return max(0.0, 1.0 - hours_old / 168.0)  # decays over one week


@dataclass
class PriorityResult:
    score: float  # 0..1
    level: str    # P1..P4
    sla_hours: int
    components: dict


def compute_priority(class_name: str, severity: SeverityResult,
                     lat: float | None = None, lon: float | None = None,
                     hours_old: float = 0.0) -> PriorityResult:
    class_risk = PROBLEM_CLASSES[class_name]["base_priority"]
    loc = location_importance(lat, lon)
    rec = recency_weight(hours_old)
    score = (W1 * class_risk + W2 * severity.score + W3 * loc + W4 * rec)
    score = min(1.0, max(0.0, score))
    level = priority_level_for_score(score)
    return PriorityResult(
        score=round(score, 3),
        level=level,
        sla_hours=SLA_HOURS[level],
        components={
            "class_risk": round(class_risk, 3),
            "severity": severity.score,
            "location": round(loc, 3),
            "recency": round(rec, 3),
            "weights": [W1, W2, W3, W4],
        },
    )
