"""City-scale reports: street health, zone heatmap, trends and forecast."""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from ..database import get_db
from ..services.analytics import forecast, street_health, trends, zone_heatmap

router = APIRouter(prefix="/api/reports", tags=["reports"])


@router.get("/heatmap")
def heatmap(db: Session = Depends(get_db)):
    """Point-level incident list for the map overlay (kept for dashboard compat)."""
    from ..models import Complaint, Detection
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
            "report_count": d.report_count or 1,
            "status": (d.work_orders[-1].status if d.work_orders else None),
        }
        for c, d in rows
    ]


@router.get("/streets")
def streets(db: Session = Depends(get_db)):
    """Per-street health index 0-100 (worst streets first)."""
    return street_health(db)


@router.get("/zones")
def zones(db: Session = Depends(get_db)):
    """Grid-cell aggregation for the intensity heatmap."""
    return zone_heatmap(db)


@router.get("/trends")
def trends_report(days: int = Query(30, ge=7, le=120), db: Session = Depends(get_db)):
    return trends(db, days=days)


@router.get("/forecast")
def forecast_report(db: Session = Depends(get_db)):
    """Heuristic next-week prediction per problem class + hotspot ranking."""
    return forecast(db)
