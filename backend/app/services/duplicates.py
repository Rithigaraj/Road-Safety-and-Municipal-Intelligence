"""Duplicate detection: same problem reported twice should not create two crews' work.

A new detection is a *duplicate* when an open detection of the same class exists
within DUPLICATE_RADIUS_M metres and DUPLICATE_WINDOW_HOURS hours. The original
issue's report_count is incremented instead of creating another work order.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from ..ml.geo import DUPLICATE_RADIUS_M, DUPLICATE_WINDOW_HOURS
from ..models import Complaint, Detection, WorkOrder


def find_duplicate(db: Session, class_name: str,
                   lat: float | None, lon: float | None) -> Detection | None:
    if lat is None or lon is None:
        return None
    cutoff = datetime.now(timezone.utc) - timedelta(hours=DUPLICATE_WINDOW_HOURS)
    rows = (
        db.query(Detection, Complaint)
        .join(Complaint, Detection.complaint_id == Complaint.id)
        .filter(
            Detection.class_name == class_name,
            Complaint.lat.isnot(None),
            ~Detection.work_orders.any(WorkOrder.status == "resolved"),
        )
        .all()
    )
    for det, complaint in rows:
        created = complaint.created_at
        if created is not None:
            if created.tzinfo is None:
                created = created.replace(tzinfo=timezone.utc)
            if created < cutoff:
                continue
        from ..ml.geo import haversine_m
        if haversine_m(lat, lon, complaint.lat, complaint.lon) <= DUPLICATE_RADIUS_M:
            return det
    return None


def register_duplicate(db: Session, duplicate_of: Detection) -> None:
    duplicate_of.report_count = (duplicate_of.report_count or 1) + 1
    db.commit()
