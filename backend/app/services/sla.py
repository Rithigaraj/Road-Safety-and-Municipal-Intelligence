"""SLA tracking + escalation.

A work order is *breached* when it is still open past its SLA window.
Escalation bumps the priority one level (P2 -> P1 ...), records who/when and
raises a notification (+ optional email).
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from ..ml.classes import PRIORITY_LEVELS, SLA_HOURS
from ..models import Detection, WorkOrder
from .notifier import notify

ORDER = ["P4", "P3", "P2", "P1"]


def _utc_ts(dt: datetime) -> float:
    """SQLite returns naive datetimes; interpret them as UTC."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.timestamp()


def sla_state(order: WorkOrder) -> dict:
    det: Detection | None = order.detection
    sla_hours = (det.sla_hours if det else None) or 168
    created = order.created_at
    now = datetime.now(timezone.utc).timestamp()
    remaining_h = None
    breached = False
    if created is not None:
        deadline = _utc_ts(created) + sla_hours * 3600
        remaining_h = round((deadline - now) / 3600, 1)
        breached = order.status != "resolved" and remaining_h < 0
    return {
        "sla_hours": sla_hours,
        "sla_remaining_hours": remaining_h,
        "sla_breached": breached,
    }


def escalate(db: Session, order: WorkOrder, by_user: str) -> WorkOrder:
    det = order.detection
    current = det.priority_level if det else "P4"
    idx = ORDER.index(current) if current in ORDER else 0
    new_level = ORDER[max(0, idx - 1)]  # one level up (P4 -> P3 ...)
    if new_level != current:
        det.priority_level = new_level
        det.sla_hours = SLA_HOURS[new_level]
        det.priority_score = min(1.0, (det.priority_score or 0.0) + 0.12)

    now = datetime.now(timezone.utc)
    order.escalated_at = now
    order.escalation_note = (
        f"{order.escalation_note or ''}"
        f"[{now:%Y-%m-%d %H:%M}] escalated {current} -> {new_level} by {by_user}\n"
    ).strip()
    db.commit()

    notify(
        db,
        ntype="escalation",
        title=f"Work order #{order.id} escalated to {new_level}",
        body=(f"{det.class_name.replace('_', ' ') if det else 'issue'} at "
              f"{det.complaint.address or 'unknown location'} escalated by {by_user}."),
        ref_type="work_order",
        ref_id=order.id,
        email=new_level == "P1",
    )
    return order


def breach_scan(db: Session) -> list[WorkOrder]:
    """Create notifications for newly-breached orders (idempotent per order)."""
    breached: list[WorkOrder] = []
    from ..models import Notification
    for order in db.query(WorkOrder).filter(WorkOrder.status != "resolved").all():
        state = sla_state(order)
        if not state["sla_breached"]:
            continue
        exists = (
            db.query(Notification)
            .filter(Notification.type == "sla_breach", Notification.ref_id == order.id)
            .count() > 0
        )
        if not exists:
            notify(
                db,
                ntype="sla_breach",
                title=f"SLA breached on work order #{order.id}",
                body=(f"{order.detection.class_name.replace('_', ' ') if order.detection else 'Issue'} "
                      f"is {abs(state['sla_remaining_hours']):.0f}h past its {state['sla_hours']}h SLA."),
                ref_type="work_order",
                ref_id=order.id,
            )
            breached.append(order)
    return breached
