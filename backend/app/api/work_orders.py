from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy.orm import Session

from ..config import UPLOAD_DIR
from ..database import get_db
from ..ml.detector import Detection as MLDetection
from ..models import User, WorkOrder
from ..schemas import WorkOrderOut, WorkOrderUpdate
from ..services.auth import require_roles
from ..services.notifier import notify
from ..services.pipeline import load_image
from ..services.sla import escalate as escalate_order, sla_state
from ..services.verification import verify
from ..services.ws import hub
from .complaints import _complaint_out, _detection_out

router = APIRouter(prefix="/api/work-orders", tags=["work-orders"])


def _out(w: WorkOrder) -> WorkOrderOut:
    det = w.detection
    complaint = det.complaint if det else None
    sla = sla_state(w)
    return WorkOrderOut(
        id=w.id,
        status=w.status,
        assignee=w.assignee,
        notes=w.notes,
        created_at=w.created_at,
        assigned_at=w.assigned_at,
        started_at=w.started_at,
        resolved_at=w.resolved_at,
        verification_status=w.verification_status,
        verification_confidence=w.verification_confidence,
        verification_note=w.verification_note,
        estimated_cost=w.estimated_cost,
        actual_cost=w.actual_cost,
        escalated_at=w.escalated_at,
        escalation_note=w.escalation_note or None,
        sla_hours=sla["sla_hours"],
        sla_remaining_hours=sla["sla_remaining_hours"],
        sla_breached=sla["sla_breached"],
        detection=_detection_out(det) if det else None,
        complaint=_complaint_out(complaint) if complaint else None,
    )


@router.get("", response_model=list[WorkOrderOut])
def list_work_orders(
    status: str | None = None,
    breached_only: bool = False,
    db: Session = Depends(get_db),
):
    q = db.query(WorkOrder)
    if status:
        q = q.filter(WorkOrder.status == status)
    orders = q.order_by(WorkOrder.id.desc()).all()
    if breached_only:
        orders = [w for w in orders if sla_state(w)["sla_breached"]]
    return [_out(w) for w in orders]


@router.get("/{order_id}", response_model=WorkOrderOut)
def get_work_order(order_id: int, db: Session = Depends(get_db)):
    order = db.get(WorkOrder, order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Work order not found")
    return _out(order)


@router.patch("/{order_id}", response_model=WorkOrderOut)
def update_work_order(
    order_id: int,
    payload: WorkOrderUpdate,
    user: User = Depends(require_roles("admin", "supervisor", "crew")),
    db: Session = Depends(get_db),
):
    order = db.get(WorkOrder, order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Work order not found")

    now = datetime.utcnow()
    became_resolved = False
    if payload.status and payload.status != order.status:
        order.status = payload.status
        if payload.status == "in_progress" and order.started_at is None:
            order.started_at = now
        elif payload.status == "resolved":
            order.resolved_at = now
            became_resolved = True
            if order.verification_status is None:
                order.verification_status = "pending"
    if payload.assignee is not None:
        order.assignee = payload.assignee
    if payload.notes is not None:
        order.notes = payload.notes
    if payload.estimated_cost is not None:
        order.estimated_cost = payload.estimated_cost
    if payload.actual_cost is not None:
        order.actual_cost = payload.actual_cost
    db.commit()
    db.refresh(order)

    det = order.detection
    hub.broadcast("work_order_updated", {
        "id": order.id, "status": order.status, "by": user.username,
        "class_name": det.class_name if det else None,
    })

    if became_resolved and det:
        notify(
            db,
            ntype="verification",
            title=f"Work order #{order.id} awaiting AI verification",
            body=(f"{det.class_name.replace('_', ' ')} marked resolved by {user.username}. "
                  f"Upload a resolution photo to verify the fix."),
            ref_type="work_order",
            ref_id=order.id,
        )
    return _out(order)


@router.post("/{order_id}/escalate", response_model=WorkOrderOut)
def escalate_work_order(
    order_id: int,
    user: User = Depends(require_roles("admin", "supervisor")),
    db: Session = Depends(get_db),
):
    """Bump priority one level (P4->P3 ... P2->P1), shorten the SLA, alert everyone."""
    order = db.get(WorkOrder, order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Work order not found")
    if order.status == "resolved":
        raise HTTPException(status_code=400, detail="Resolved orders cannot be escalated.")
    order = escalate_order(db, order, by_user=user.username)
    return _out(order)


@router.post("/{order_id}/verify", response_model=WorkOrderOut)
async def verify_work_order(
    order_id: int,
    file: UploadFile = File(...),
    user: User = Depends(require_roles("admin", "supervisor", "crew")),
    db: Session = Depends(get_db),
):
    """Upload a resolution photo; the same AI pipeline re-inspects the site."""
    order = db.get(WorkOrder, order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Work order not found")
    if order.status != "resolved":
        raise HTTPException(status_code=400, detail="Only resolved work orders can be verified.")

    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="Empty image uploaded.")

    name = f"verify_{order_id}_{datetime.now().strftime('%Y%m%d%H%M%S')}.jpg"
    path = UPLOAD_DIR / name
    path.write_bytes(data)

    from ..ml.detector import get_detector

    detector = get_detector()
    det = order.detection
    original = MLDetection(
        class_name=det.class_name,
        confidence=det.confidence,
        bbox=(det.bbox_x1, det.bbox_y1, det.bbox_x2, det.bbox_y2),
        evidence={},
    )
    found = detector.detect(load_image(data))
    result = verify(original, found, original_severity=det.severity_score)
    order.verification_status = result.status
    order.verification_confidence = result.confidence
    order.verification_note = result.note
    order.resolution_image_path = str(path.relative_to(Path(__file__).resolve().parent.parent.parent))
    db.commit()

    notify(
        db,
        ntype="verification",
        title=f"Fix {'verified' if result.status == 'verified' else result.status} - order #{order.id}",
        body=result.note,
        ref_type="work_order",
        ref_id=order.id,
        email=result.status == "failed",
    )
    hub.broadcast("verification", {"id": order.id, "status": result.status})
    db.refresh(order)
    return _out(order)
