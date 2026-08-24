from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Complaint, Detection, WorkOrder
from ..schemas import WorkOrderOut

router = APIRouter(prefix="/api", tags=["dashboard"])


@router.get("/dashboard/stats")
def dashboard_stats(db: Session = Depends(get_db)):
    total_complaints = db.query(func.count(Complaint.id)).scalar() or 0
    total_detections = db.query(func.count(Detection.id)).scalar() or 0
    open_work = db.query(func.count(WorkOrder.id)).filter(WorkOrder.status != "resolved").scalar() or 0
    resolved = db.query(func.count(WorkOrder.id)).filter(WorkOrder.status == "resolved").scalar() or 0
    verified = db.query(func.count(WorkOrder.id)).filter(WorkOrder.verification_status == "verified").scalar() or 0

    by_class = [
        {"class_name": c, "count": n}
        for c, n in db.query(Detection.class_name, func.count(Detection.id))
        .group_by(Detection.class_name).all()
    ]
    by_severity = [
        {"severity": s, "count": n}
        for s, n in db.query(Detection.severity, func.count(Detection.id))
        .group_by(Detection.severity).all()
    ]
    by_priority = [
        {"level": p, "count": n}
        for p, n in db.query(Detection.priority_level, func.count(Detection.id))
        .group_by(Detection.priority_level).all()
    ]
    by_status = [
        {"status": s, "count": n}
        for s, n in db.query(WorkOrder.status, func.count(WorkOrder.id))
        .group_by(WorkOrder.status).all()
    ]
    by_department = [
        {"department": d, "count": n}
        for d, n in db.query(Detection.department_code, func.count(Detection.id))
        .group_by(Detection.department_code).all()
    ]

    # SLA compliance: resolved before sla_hours elapsed
    sla_ok = 0
    sla_total = 0
    for w in db.query(WorkOrder).filter(WorkOrder.resolved_at.isnot(None)).all():
        if w.detection and w.detection.sla_hours:
            sla_total += 1
            elapsed = (w.resolved_at - w.created_at).total_seconds() / 3600
            if elapsed <= w.detection.sla_hours:
                sla_ok += 1
    sla_compliance = round(sla_ok / sla_total, 3) if sla_total else 1.0

    return {
        "total_complaints": total_complaints,
        "total_detections": total_detections,
        "open_work": open_work,
        "resolved": resolved,
        "verified": verified,
        "sla_compliance": sla_compliance,
        "by_class": by_class,
        "by_severity": by_severity,
        "by_priority": by_priority,
        "by_status": by_status,
        "by_department": by_department,
    }


@router.get("/reports/heatmap")
def heatmap(db: Session = Depends(get_db)):
    rows = (
        db.query(Complaint, Detection)
        .join(Detection, Detection.complaint_id == Complaint.id)
        .filter(Complaint.lat.isnot(None), Complaint.lon.isnot(None))
        .all()
    )
    return [
        {
            "lat": c.lat, "lon": c.lon,
            "class_name": d.class_name,
            "severity": d.severity,
            "priority_level": d.priority_level,
            "status": (db.query(WorkOrder.status)
                       .filter(WorkOrder.detection_id == d.id)
                       .order_by(WorkOrder.id.desc()).first() or ("no_order",))[0],
        }
        for c, d in rows
    ]
