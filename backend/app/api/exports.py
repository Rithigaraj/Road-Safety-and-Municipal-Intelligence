"""CSV exports for records/RTI use."""
import csv
import io

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Complaint, Detection, WorkOrder
from ..services.sla import sla_state

router = APIRouter(prefix="/api/export", tags=["export"])


def _csv_response(filename: str, header: list[str], rows: list[list]) -> StreamingResponse:
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(header)
    writer.writerows(rows)
    buf.seek(0)
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/work-orders.csv")
def export_work_orders(db: Session = Depends(get_db)):
    rows = []
    for w in db.query(WorkOrder).order_by(WorkOrder.id).all():
        det = w.detection
        c = det.complaint if det else None
        sla = sla_state(w)
        rows.append([
            w.id, w.status, w.assignee,
            det.class_name if det else "", det.severity if det else "",
            det.priority_level if det else "", det.department_code if det else "",
            c.tracking_code if c else "", c.address if c else "",
            w.created_at.isoformat() if w.created_at else "",
            w.resolved_at.isoformat() if w.resolved_at else "",
            w.verification_status or "",
            w.estimated_cost if w.estimated_cost is not None else "",
            w.actual_cost if w.actual_cost is not None else "",
            "yes" if sla["sla_breached"] else "no",
        ])
    return _csv_response(
        "work_orders.csv",
        ["id", "status", "assignee", "class", "severity", "priority", "department",
         "tracking_code", "address", "created_at", "resolved_at",
         "verification", "estimated_cost_inr", "actual_cost_inr", "sla_breached"],
        rows,
    )


@router.get("/complaints.csv")
def export_complaints(db: Session = Depends(get_db)):
    rows = []
    for c in db.query(Complaint).order_by(Complaint.id).all():
        for d in c.detections:
            rows.append([
                c.id, c.tracking_code or "", c.source, c.created_at.isoformat(),
                c.lat if c.lat is not None else "", c.lon if c.lon is not None else "",
                c.address or "",
                d.class_name, round(d.confidence, 3), d.severity,
                d.priority_level or "", d.department_code or "",
                d.size_estimate_cm if d.size_estimate_cm is not None else "",
                d.report_count or 1, "duplicate" if d.duplicate_of_id else "original",
            ])
    return _csv_response(
        "complaints.csv",
        ["complaint_id", "tracking_code", "source", "created_at", "lat", "lon", "address",
         "class", "confidence", "severity", "priority", "department",
         "size_cm", "report_count", "dedup_status"],
        rows,
    )
