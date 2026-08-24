"""Crew dispatch: order the day's open fixes into an efficient driving route.

Nearest-neighbour construction + 2-opt improvement over the open work orders
of a department. Pure-python, no external solver needed for MVP scale.
"""
from __future__ import annotations

from ..ml.geo import CITY_CENTER, haversine_m
from ..models import Detection, WorkOrder


def _two_opt(stops: list[dict]) -> list[dict]:
    def total(route):
        pts = [(CITY_CENTER[1], CITY_CENTER[0])] + [(s["lat"], s["lon"]) for s in route]
        return sum(haversine_m(pts[i][0], pts[i][1], pts[i + 1][0], pts[i + 1][1])
                   for i in range(len(pts) - 1))

    improved = True
    best = list(stops)
    while improved:
        improved = False
        base = total(best)
        for i in range(1, len(best) - 1):
            for j in range(i + 1, len(best)):
                candidate = best[:i] + best[i:j + 1][::-1] + best[j + 1:]
                if total(candidate) < base - 1.0:  # >1 m improvement
                    best = candidate
                    improved = True
                    break
            if improved:
                break
    return best


def build_route(db, department_code: str | None = None, max_stops: int = 40) -> dict:
    q = (
        db.query(WorkOrder, Detection)
        .join(Detection, WorkOrder.detection_id == Detection.id)
        .filter(WorkOrder.status != "resolved")
    )
    if department_code:
        q = q.filter(Detection.department_code == department_code)

    rows = q.all()
    stops = []
    for order, det in rows:
        c = det.complaint
        if c.lat is None or c.lon is None:
            continue
        stops.append({
            "work_order_id": order.id,
            "detection_id": det.id,
            "class_name": det.class_name,
            "priority_level": det.priority_level,
            "severity": det.severity,
            "address": c.address,
            "lat": c.lat,
            "lon": c.lon,
        })

    # highest priority first as seeds, then optimise the geometry
    stops.sort(key=lambda s: (s["priority_level"] or "P4"), reverse=False)
    stops = stops[:max_stops]

    depot = (CITY_CENTER[1], CITY_CENTER[0])
    remaining = list(stops)
    route = []
    cur = depot
    total_km = 0.0
    while remaining:
        nxt = min(remaining, key=lambda s: haversine_m(cur[0], cur[1], s["lat"], s["lon"]))
        leg = haversine_m(cur[0], cur[1], nxt["lat"], nxt["lon"])
        total_km += leg
        route.append({**nxt, "leg_km": round(leg / 1000.0, 2)})
        cur = (nxt["lat"], nxt["lon"])
        remaining.remove(nxt)

    route = _two_opt(route)
    # recompute legs after optimisation
    cur = depot
    total_km = 0.0
    for stop in route:
        leg = haversine_m(cur[0], cur[1], stop["lat"], stop["lon"])
        stop["leg_km"] = round(leg / 1000.0, 2)
        total_km += leg
        cur = (stop["lat"], stop["lon"])

    return {
        "department_code": department_code,
        "stops": route,
        "total_km": round(total_km / 1000.0, 2),
        "depot": {"lat": CITY_CENTER[1], "lon": CITY_CENTER[0]},
    }
