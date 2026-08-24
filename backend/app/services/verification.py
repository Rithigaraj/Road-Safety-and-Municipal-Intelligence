"""AI verification: after a work order is marked resolved, re-inspect the site.

The resolution photo is run through the same detector. The fix is deemed
verified when the original problem class is no longer detected with the same
severity, or a repair photo shows significant improvement.
"""
from __future__ import annotations

from dataclasses import dataclass

from ..ml.detector import Detection
from ..ml.severity import compute_severity


@dataclass
class VerificationResult:
    status: str  # verified | failed | inconclusive
    confidence: float
    note: str


def verify(original: Detection, detections: list[Detection], min_improvement: float = 0.3,
           original_severity: float | None = None) -> VerificationResult:
    """`original` is the pre-fix detection; `detections` come from the resolution photo.

    `original_severity` overrides the recomputed baseline when the caller already
    has the persisted severity score (recommended - it includes full evidence).
    """
    if original_severity is not None:
        original_sev = float(original_severity)
    else:
        original_sev = compute_severity(original).score

    match = [d for d in detections if d.class_name == original.class_name]
    if not match:
        # the problem class is gone entirely -> verified
        return VerificationResult("verified", 0.95,
                                  "Problem class no longer present in verification photo.")

    worst = max(match, key=lambda d: d.confidence)
    new_sev = compute_severity(worst).score
    if new_sev <= original_sev - min_improvement:
        return VerificationResult(
            "verified", round(0.6 + 0.4 * (original_sev - new_sev), 3),
            f"Severity improved from {original_sev:.2f} to {new_sev:.2f} "
            f"(confidence {worst.confidence:.2f}).")
    if new_sev <= original_sev:
        return VerificationResult(
            "inconclusive", round(0.5 + 0.3 * (original_sev - new_sev), 3),
            "Slight improvement detected; manual review recommended.")
    return VerificationResult(
        "failed", round(new_sev, 3),
        f"Problem still present with severity {new_sev:.2f} (>= {original_sev:.2f}). "
        f"Fix not verified.")
