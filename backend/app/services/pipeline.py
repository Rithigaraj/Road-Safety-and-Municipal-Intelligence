"""Inference pipeline: image -> detections -> severity -> priority -> assignment.

This is the orchestrator the API layer calls. Pure analysis (no DB writes) is
exposed for the /analyze endpoint; process_complaint persists the full chain,
links duplicate reports, estimates repair cost and raises notifications.
"""
from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO

from PIL import Image
from sqlalchemy.orm import Session

from ..ml.assignment import assign
from ..ml.detector import Detection
from ..ml.exif import gps_from_bytes
from ..ml.priority import compute_priority
from ..ml.severity import compute_severity
from ..models import Complaint, Detection as DetectionModel, WorkOrder
from .duplicates import find_duplicate
from .notifier import notify
from .ws import hub


@dataclass
class AnalyzedDetection:
    detection: Detection
    severity_label: str
    severity_score: float
    priority_score: float
    priority_level: str
    sla_hours: int
    department_code: str
    size_estimate_cm: float | None = None
    is_duplicate: bool = False


def load_image(data: bytes) -> Image.Image:
    return Image.open(BytesIO(data)).convert("RGB")


def analyze(data: bytes, lat: float | None = None, lon: float | None = None,
            hours_old: float = 0.0, detector=None, max_detections: int = 3) -> list[AnalyzedDetection]:
    """Run the full analysis chain without persisting anything."""
    from ..ml.detector import get_detector as build_detector
    detector = detector or build_detector()
    image = load_image(data)
    raw = detector.detect(image)[:max_detections]
    results: list[AnalyzedDetection] = []
    for det in raw:
        sev = compute_severity(det)
        prio = compute_priority(det.class_name, sev, lat=lat, lon=lon,
                                hours_old=hours_old)
        asg = assign(det.class_name, {})
        results.append(AnalyzedDetection(
            detection=det,
            severity_label=sev.label,
            severity_score=sev.score,
            priority_score=prio.score,
            priority_level=prio.level,
            sla_hours=prio.sla_hours,
            department_code=asg.department_code,
            size_estimate_cm=sev.size_estimate_cm,
        ))
    return results


def _open_counts(db: Session) -> dict[str, int]:
    from sqlalchemy import func
    rows = (
        db.query(DetectionModel.department_code, func.count(DetectionModel.id))
        .filter(~DetectionModel.work_orders.any(WorkOrder.status == "resolved"))
        .group_by(DetectionModel.department_code)
        .all()
    )
    return {code: count for code, count in rows}


BASE_REPAIR_COST_INR = {
    "pothole": 12000, "road_crack": 5000, "garbage": 2500,
    "broken_streetlight": 4500, "water_leakage": 15000,
    "damaged_traffic_sign": 6000, "blocked_drainage": 8000,
}
SEVERITY_COST_MULT = {"low": 0.8, "medium": 1.0, "high": 1.4, "critical": 1.9}


def estimate_cost(class_name: str, severity: str) -> float:
    base = BASE_REPAIR_COST_INR.get(class_name, 3000)
    return round(base * SEVERITY_COST_MULT.get(severity, 1.0))


def process_complaint(db: Session, complaint: Complaint, data: bytes,
                      detector=None) -> list[AnalyzedDetection]:
    """Persist a complaint + its detections + auto-created work orders."""
    # zero-typing reports: fall back to the camera's EXIF GPS tag
    if complaint.lat is None or complaint.lon is None:
        gps = gps_from_bytes(data)
        if gps:
            complaint.lat, complaint.lon = gps

    results = analyze(data, lat=complaint.lat, lon=complaint.lon, detector=detector)
    open_counts = _open_counts(db)
    queue_seen: dict[str, int] = {}
    top = results[0] if results else None

    for r in results:
        x1, y1, x2, y2 = r.detection.bbox
        common = dict(
            complaint_id=complaint.id,
            class_name=r.detection.class_name,
            confidence=r.detection.confidence,
            bbox_x1=x1, bbox_y1=y1, bbox_x2=x2, bbox_y2=y2,
            severity=r.severity_label,
            severity_score=r.severity_score,
            priority_score=r.priority_score,
            priority_level=r.priority_level,
            sla_hours=r.sla_hours,
            size_estimate_cm=r.size_estimate_cm,
        )

        original = find_duplicate(db, r.detection.class_name, complaint.lat, complaint.lon)
        if original is not None:
            # same issue re-reported: bump the counter, no second work order
            original.report_count = (original.report_count or 1) + 1
            det = DetectionModel(department_code=original.department_code,
                                 queue_position=original.queue_position or 1,
                                 duplicate_of_id=original.id, **common)
            db.add(det)
            db.flush()
            r.is_duplicate = True
            continue

        asg = assign(r.detection.class_name, open_counts)
        queue_seen[asg.department_code] = queue_seen.get(asg.department_code, 0) + 1
        qpos = open_counts.get(asg.department_code, 0) + queue_seen[asg.department_code]

        det = DetectionModel(
            department_code=asg.department_code,
            queue_position=qpos,
            **common,
        )
        db.add(det)
        db.flush()

        cost = estimate_cost(r.detection.class_name, r.severity_label)
        db.add(WorkOrder(
            detection_id=det.id,
            status="assigned",
            assigned_at=complaint.created_at,
            assignee=asg.department_name,
            estimated_cost=cost * (det.report_count or 1),
        ))

        where = complaint.address or (
            f"{complaint.lat:.5f}, {complaint.lon:.5f}" if complaint.lat else "location unknown")
        notify(
            db,
            ntype="new_complaint",
            title=f"New {r.priority_level} issue: {r.detection.class_name.replace('_', ' ')}",
            body=(f"{r.detection.class_name.replace('_', ' ')} ({r.severity_label}, "
                  f"~{r.size_estimate_cm:.0f} cm) at {where}. "
                  f"Routed to {asg.department_name}." if r.size_estimate_cm else
                  f"{r.detection.class_name.replace('_', ' ')} ({r.severity_label}) at {where}. "
                  f"Routed to {asg.department_name}."),
            ref_type="work_order",
            ref_id=det.id,
            email=r.priority_level == "P1",
        )

    db.commit()
    hub.broadcast("new_complaint", {
        "complaint_id": complaint.id,
        "tracking_code": complaint.tracking_code,
        "top_class": top.detection.class_name if top else None,
        "count": len(results),
    })
    return results
