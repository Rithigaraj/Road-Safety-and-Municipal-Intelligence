"""Seed the demo database.

Processes the synthetic sample images through the full pipeline
(image -> detection -> severity -> priority -> department) and creates
complaints + work orders, including a few in-progress/resolved states so
the dashboard has meaningful data on first load.

Usage:  python -m scripts.seed_db
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.database import SessionLocal, engine
from app.ml.classes import DEPARTMENTS, DEPARTMENT_IDS
from app.models import Complaint, Department, WorkOrder
from app.services.pipeline import process_complaint

SAMPLES = Path(__file__).resolve().parent.parent / "data" / "samples"

# (file, source, lat, lon, address, description, hours_old)
COMPLAINTS = [
    ("pothole.jpg", "citizen", 12.9791, 77.5913, "MG Road", "Deep pothole near the bus stop, vehicles are swerving.", 6.0),
    ("road_crack.jpg", "cctv", 12.9650, 77.6107, "100 Feet Road", "Long surface crack widening along the main carriageway.", 30.0),
    ("garbage.jpg", "citizen", 12.9506, 77.6010, "Kammanahalli", "Illegal dumping of mixed waste on the service road.", 18.0),
    ("broken_streetlight.jpg", "dashcam", 12.9823, 77.5875, "Cubbon Park", "Streetlight on the service lane has been out for nights.", 96.0),
    ("water_leakage.jpg", "citizen", 12.9719, 77.5945, "Mahatma Gandhi Road", "Water leaking from a broken main, flooding the footpath.", 4.0),
    ("damaged_traffic_sign.jpg", "cctv", 12.9588, 77.6168, "Indiranagar", "Direction sign damaged with a missing panel and cracks.", 20.0),
    ("blocked_drainage.jpg", "citizen", 12.9390, 77.6263, "Banaswadi", "Drain fully blocked by debris, water pooling on the road.", 9.0),
]

EXTRA = [
    ("pothole.jpg", "cctv", 12.9341, 77.6230, "Hennur Road", "Multiple potholes after the rain.", 48.0),
    ("garbage.jpg", "citizen", 12.9716, 77.5812, "Vasanth Nagar", "Overflowing garbage in front of the community hall.", 12.0),
]


def main() -> None:
    from scripts.generate_samples import main as generate

    generate()

    from app.database import Base

    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)

    db = SessionLocal()
    try:
        for code, info in DEPARTMENTS.items():
            db.add(Department(id=DEPARTMENT_IDS[code], code=code, name=info["name"], color=info["color"]))
        db.commit()

        from app.services.auth import seed_default_users
        seed_default_users(db)

        all_rows = COMPLAINTS + EXTRA
        for fname, source, lat, lon, addr, desc, hours_old in all_rows:
            data = (SAMPLES / fname).read_bytes()
            c = Complaint(source=source, description=desc, lat=lat, lon=lon, address=addr,
                          image_path=f"data/samples/{fname}")
            db.add(c)
            db.flush()
            process_complaint(db, c, data)
        db.commit()

        # simulate some progress
        orders = db.query(WorkOrder).order_by(WorkOrder.id).all()
        from datetime import datetime, timedelta, timezone

        now = datetime.now(timezone.utc)
        # 1) one assigned order moved to in_progress
        if orders:
            o = orders[0]
            o.status = "in_progress"
            o.started_at = now - timedelta(hours=2)
        # 2) one order resolved and AI-verified
        if len(orders) > 1:
            o = orders[1]
            o.status = "resolved"
            o.started_at = now - timedelta(hours=20)
            o.resolved_at = now - timedelta(hours=6)
            o.verification_status = "verified"
            o.verification_confidence = 0.94
            o.verification_note = "Problem class no longer present in verification photo."
            o.notes = "Patch applied; site re-photographed and verified by AI."
        # 3) one order resolved but pending AI verification
        if len(orders) > 2:
            o = orders[2]
            o.status = "resolved"
            o.started_at = now - timedelta(hours=30)
            o.resolved_at = now - timedelta(hours=3)
            o.verification_status = "pending"
            o.notes = "Crew reports completion; awaiting verification photo."
        db.commit()
    finally:
        db.close()

    print(f"Seeded {len(all_rows)} complaints.")


if __name__ == "__main__":
    sys.exit(main())
