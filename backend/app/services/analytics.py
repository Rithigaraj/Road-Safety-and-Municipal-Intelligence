"""Analytics: street health index, zone heatmap, trends and a simple forecast.

All aggregations run in SQL/pandas-free python over SQLAlchemy queries so the
MVP stays dependency-light.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta, timezone

from sqlalchemy import func
from sqlalchemy.orm import Session

from ..ml.geo import haversine_m
from ..models import Complaint, Detection, WorkOrder

SEVERITY_WEIGHT = {"low": 1, "medium": 3, "high": 6, "critical": 10}
GRID_CELLS = 12  # 12x12 grid over the city bounding box


# ---------------------------------------------------------------- streets

def street_health(db: Session) -> list[dict]:
    """0-100 health index per address; open issues drag the score down."""
    rows = (
        db.query(Complaint.address, Detection)
        .join(Detection, Detection.complaint_id == Complaint.id)
        .all()
    )
    agg: dict[str, dict] = {}
    for address, det in rows:
        key = (address or "Unspecified location").strip()
        a = agg.setdefault(key, {"open": 0, "penalty": 0.0, "total": 0})
        a["total"] += 1
        resolved = any(w.status == "resolved" for w in det.work_orders)
        if not resolved:
            a["open"] += 1
            a["penalty"] += SEVERITY_WEIGHT.get(det.severity, 2) * min(det.report_count or 1, 5)

    out = []
    for address, a in agg.items():
        score = max(0.0, 100.0 - a["penalty"])
        out.append({
            "address": address,
            "open_issues": a["open"],
            "total_reports": a["total"],
            "health_index": round(score),
        })
    out.sort(key=lambda s: s["health_index"])
    return out


# ---------------------------------------------------------------- zones

def zone_heatmap(db: Session) -> list[dict]:
    """Aggregate incidents into grid cells for a polygon heatmap."""
    pts = (
        db.query(Complaint.lat, Complaint.lon, Detection.severity, Detection.report_count)
        .join(Detection, Detection.complaint_id == Complaint.id)
        .filter(Complaint.lat.isnot(None), Complaint.lon.isnot(None))
        .all()
    )
    if not pts:
        return []

    lats = [p[0] for p in pts]
    lons = [p[1] for p in pts]
    pad = 0.01
    lat_min, lat_max = min(lats) - pad, max(lats) + pad
    lon_min, lon_max = min(lons) - pad, max(lons) + pad
    dlat = (lat_max - lat_min) / GRID_CELLS
    dlon = (lon_max - lon_min) / GRID_CELLS

    cells: dict[tuple[int, int], dict] = {}
    for lat, lon, severity, reports in pts:
        ix = min(int((lat - lat_min) / dlat), GRID_CELLS - 1)
        iy = min(int((lon - lon_min) / dlon), GRID_CELLS - 1)
        cell = cells.setdefault((ix, iy), {"count": 0, "intensity": 0.0})
        cell["count"] += 1
        cell["intensity"] += SEVERITY_WEIGHT.get(severity, 2) * min(reports or 1, 5)

    max_intensity = max(c["intensity"] for c in cells.values()) or 1.0
    out = []
    for (ix, iy), c in cells.items():
        out.append({
            "lat_min": round(lat_min + ix * dlat, 6),
            "lat_max": round(lat_min + (ix + 1) * dlat, 6),
            "lon_min": round(lon_min + iy * dlon, 6),
            "lon_max": round(lon_min + (iy + 1) * dlon, 6),
            "count": c["count"],
            "intensity": round(c["intensity"] / max_intensity, 3),
        })
    return out


# ---------------------------------------------------------------- trends

def _naive(dt: datetime) -> datetime:
    return dt.replace(tzinfo=None) if dt.tzinfo else dt


def _day_key(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%d")


def trends(db: Session, days: int = 30) -> dict:
    now = datetime.now(timezone.utc)
    start = now - timedelta(days=days)

    detections = (
        db.query(Detection.class_name, Complaint.created_at, Detection.severity)
        .join(Complaint, Detection.complaint_id == Complaint.id)
        .filter(Complaint.created_at >= _naive(start))
        .all()
    )
    per_day: dict[str, dict] = defaultdict(lambda: {"count": 0})
    by_class_total: dict[str, int] = defaultdict(int)
    for class_name, created, _sev in detections:
        day = _day_key(created)
        per_day[day]["count"] += 1
        by_class_total[class_name] += 1

    series = []
    for i in range(days):
        day = _day_key(now - timedelta(days=days - 1 - i))
        series.append({"date": day, "count": per_day.get(day, {}).get("count", 0)})

    # resolution time per completed day (orders resolved that day)
    resolved_rows = db.query(WorkOrder).filter(
        WorkOrder.resolved_at.isnot(None),
        WorkOrder.resolved_at >= _naive(start),
    ).all()
    res_per_day: dict[str, list[float]] = defaultdict(list)
    for w in resolved_rows:
        hours = (w.resolved_at - w.created_at).total_seconds() / 3600
        res_per_day[_day_key(w.resolved_at)].append(round(hours, 1))

    resolution_series = [
        {
            "date": _day_key(now - timedelta(days=days - 1 - i)),
            "avg_hours": (round(sum(v) / len(v), 1) if (v := res_per_day.get(day)) else None),
        }
        for i in range(days)
        for day in [_day_key(now - timedelta(days=days - 1 - i))]
    ]

    return {
        "detections_per_day": series,
        "avg_resolution_hours": resolution_series,
        "by_class_total": dict(by_class_total),
    }


def _naive(dt: datetime) -> datetime:
    return dt.replace(tzinfo=None) if dt.tzinfo else dt


# ---------------------------------------------------------------- forecast

def forecast(db: Session) -> dict:
    """Heuristic next-7-day prediction from the last four weeks of data."""
    now = datetime.utcnow()
    start28 = now - timedelta(days=28)
    start14 = now - timedelta(days=14)

    rows = (
        db.query(Detection.class_name, Complaint.created_at, Complaint.lat, Complaint.lon)
        .join(Complaint, Detection.complaint_id == Complaint.id)
        .filter(Complaint.created_at >= start28)
        .all()
    )

    recent: dict[str, int] = defaultdict(int)
    older: dict[str, int] = defaultdict(int)
    hotspots: dict[tuple[float, float], float] = defaultdict(float)
    for class_name, created, lat, lon in rows:
        if created >= start14:
            recent[class_name] += 1
        else:
            older[class_name] += 1
        if lat is not None and lon is not None:
            hotspots[(round(lat, 3), round(lon, 3))] += 1.0

    per_class = []
    all_classes = set(recent) | set(older)
    for cls in sorted(all_classes):
        r, o = recent[cls], older[cls]
        base = r / 2.0  # avg per week over the last two weeks
        trend = 1.0
        if o > 0:
            trend = min(2.0, max(0.25, (r / 2.0) / (o / 2.0)))
        elif r > 0:
            trend = 1.5  # brand new problem source
        per_class.append({
            "class_name": cls,
            "last_week_count": r,
            "trend": round(trend, 2),
            "predicted_next_week": max(0, round(base * trend)),
        })
    per_class.sort(key=lambda x: x["predicted_next_week"], reverse=True)

    top_hotspots = sorted(hotspots.items(), key=lambda kv: kv[1], reverse=True)[:5]
    return {
        "per_class": per_class,
        "hotspots": [
            {"lat": k[0], "lon": k[1], "reports_last_4_weeks": int(v)}
            for k, v in top_hotspots
        ],
        "note": "heuristic moving-average forecast with trend factor; not a statistical model",
    }
