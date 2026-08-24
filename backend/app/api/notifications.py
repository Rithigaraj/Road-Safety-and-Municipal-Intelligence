from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Notification
from ..schemas import NotificationOut
from ..services.sla import breach_scan

router = APIRouter(prefix="/api/notifications", tags=["notifications"])


@router.get("", response_model=list[NotificationOut])
def list_notifications(only_unread: bool = False,
                       db: Session = Depends(get_db)):
    q = db.query(Notification)
    if only_unread:
        q = q.filter(Notification.read.is_(False))
    return q.order_by(Notification.created_at.desc()).limit(100).all()


@router.get("/unread-count")
def unread_count(db: Session = Depends(get_db)):
    return {"count": db.query(func.count(Notification.id))
                        .filter(Notification.read.is_(False)).scalar() or 0}


@router.post("/sla-scan")
def run_sla_scan(db: Session = Depends(get_db)):
    """Check every open order against its SLA; notify on fresh breaches."""
    breached = breach_scan(db)
    return {"newly_breached": [{"id": w.id} for w in breached]}


@router.post("/{notification_id}/read")
def mark_read(notification_id: int, db: Session = Depends(get_db)):
    n = db.get(Notification, notification_id)
    if not n:
        raise HTTPException(status_code=404, detail="Notification not found")
    n.read = True
    db.commit()
    return {"ok": True}


@router.post("/read-all")
def mark_all_read(db: Session = Depends(get_db)):
    db.query(Notification).filter(Notification.read.is_(False)) \
      .update({"read": True}, synchronize_session=False)
    db.commit()
    return {"ok": True}
