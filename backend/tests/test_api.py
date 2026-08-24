import os
import tempfile
from pathlib import Path

# Use an isolated database before importing the app.
_tmp = tempfile.mkdtemp()
os.environ["DATABASE_URL"] = f"sqlite:///{Path(_tmp) / 'test.db'}"
os.environ["DETECTOR_BACKEND"] = "heuristic"

from fastapi.testclient import TestClient  # noqa: E402

from app.database import Base, SessionLocal, engine  # noqa: E402
from app.ml.classes import DEPARTMENTS, DEPARTMENT_IDS  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Department  # noqa: E402
from app.services.auth import hash_password, seed_default_users  # noqa: E402

# create schema + departments + users up front (TestClient bypasses startup hooks)
Base.metadata.create_all(bind=engine)
_db = SessionLocal()
if not _db.query(Department).count():
    for code, info in DEPARTMENTS.items():
        _db.add(Department(id=DEPARTMENT_IDS[code], code=code,
                           name=info["name"], color=info["color"]))
    _db.commit()
seed_default_users(_db)
_db.close()

SAMPLES = Path(__file__).resolve().parent.parent / "data" / "samples"

client = TestClient(app)

AUTH = {}          # filled by the login fixture below
ANON_AUTH_FAIL = 401


def _login(username: str, password: str) -> dict:
    r = client.post("/api/auth/login", json={"username": username, "password": password})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def _sample(name: str) -> bytes:
    return (SAMPLES / name).read_bytes()


def _staff_headers() -> dict:
    if not AUTH:
        AUTH.update(_login("admin", "admin123"))
    return AUTH


def test_health():
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_auth_login_and_me():
    headers = _staff_headers()
    r = client.get("/api/auth/me", headers=headers)
    assert r.status_code == 200
    assert r.json()["role"] == "admin"

    # wrong credentials rejected
    r = client.post("/api/auth/login",
                    json={"username": "admin", "password": "nope"})
    assert r.status_code == 401

    # crew cannot create users
    crew = _login("crew", "crew123")
    r = client.post("/api/auth/users", headers=crew,
                    json={"username": "x", "password": "x12345", "role": "crew"})
    assert r.status_code == 403


def test_analyze_water_leakage():
    r = client.post("/api/complaints/analyze",
                    files={"file": ("water.jpg", _sample("water_leakage.jpg"), "image/jpeg")},
                    data={"lat": "12.97", "lon": "77.59"})
    assert r.status_code == 200
    body = r.json()
    assert body["top_class"] == "water_leakage"
    assert body["top_severity"] in {"low", "medium", "high", "critical"}
    assert body["top_priority_level"].startswith("P")
    assert body["top_department"] == "water_supply"


def test_create_complaint_has_tracking_code():
    r = client.post("/api/complaints",
                    files={"file": ("pothole.jpg", _sample("pothole.jpg"), "image/jpeg")},
                    data={"source": "citizen", "lat": "12.99", "lon": "77.60",
                          "address": "Test street", "description": "deep hole"})
    assert r.status_code == 201
    complaint = r.json()
    assert complaint["tracking_code"].startswith("RSM-")
    assert any(d["class_name"] == "pothole" for d in complaint["detections"])

    # public tracking lookup
    r = client.get(f"/api/complaints/track/{complaint['tracking_code']}")
    assert r.status_code == 200
    assert r.json()["id"] == complaint["id"]

    r = client.get("/api/complaints/track/RSM-DOESNOTEXIST")
    assert r.status_code == 404


def test_duplicate_reports_do_not_spawn_extra_work_orders():
    data = {"lat": "13.0100", "lon": "77.5500", "address": "Dup lane"}
    files = {"file": ("dup.jpg", _sample("pothole.jpg"), "image/jpeg")}
    first = client.post("/api/complaints", files=files, data=data).json()
    second = client.post("/api/complaints", files=files, data=data).json()
    orig = next(d for d in first["detections"])
    dup = [d for d in second["detections"] if d["is_duplicate"]]
    assert dup, "second report should be linked as duplicate"
    assert dup[0]["duplicate_of_id"] == orig["id"]
    orders_same_spot = [
        o for o in client.get("/api/work-orders").json()
        if o["complaint"]["address"] == "Dup lane"
    ]
    assert len(orders_same_spot) == 1
    # original issue's counter went up
    refreshed = client.get(f"/api/work-orders/{orders_same_spot[0]['id']}").json()
    assert refreshed["detection"]["report_count"] >= 2


def test_workflow_requires_auth():
    r = client.patch("/api/work-orders/999999", json={"status": "in_progress"})
    assert r.status_code == ANON_AUTH_FAIL
    r = client.get("/api/dispatch/route")
    assert r.status_code == ANON_AUTH_FAIL


def test_full_workflow_with_costs_and_escalation():
    headers = _staff_headers()
    r = client.post("/api/complaints",
                    files={"file": ("wf.jpg", _sample("pothole.jpg"), "image/jpeg")},
                    data={"lat": "12.98", "lon": "77.64", "address": "Workflow way"})
    assert r.status_code == 201
    order_id = client.get("/api/work-orders").json()[0]["id"]

    r = client.patch(f"/api/work-orders/{order_id}", headers=headers,
                     json={"status": "in_progress", "assignee": "Crew A",
                           "estimated_cost": 9000})
    assert r.status_code == 200
    body = r.json()
    assert body["estimated_cost"] == 9000
    assert body["started_at"] is not None
    assert "sla_remaining_hours" in body

    r = client.post(f"/api/work-orders/{order_id}/escalate", headers=headers)
    assert r.status_code == 200
    assert r.json()["escalated_at"] is not None

    r = client.patch(f"/api/work-orders/{order_id}", headers=headers,
                     json={"status": "resolved"})
    assert r.status_code == 200
    assert r.json()["verification_status"] == "pending"

    r = client.post(f"/api/work-orders/{order_id}/verify", headers=headers,
                    files={"file": ("clean.jpg", _sample("clean_road.jpg"), "image/jpeg")})
    assert r.status_code == 200
    assert r.json()["verification_status"] == "verified"


def test_notifications_feed():
    r = client.get("/api/notifications")
    assert r.status_code == 200
    assert isinstance(r.json(), list)
    r = client.get("/api/notifications/unread-count")
    assert r.status_code == 200 and "count" in r.json()


def test_reports_endpoints():
    for path in ("/api/reports/heatmap", "/api/reports/streets",
                 "/api/reports/zones", "/api/reports/trends",
                 "/api/reports/forecast"):
        r = client.get(path)
        assert r.status_code == 200, path


def test_dispatch_route():
    r = client.get("/api/dispatch/route", headers=_staff_headers())
    assert r.status_code == 200
    body = r.json()
    assert "stops" in body and "total_km" in body


def test_exports():
    for path in ("/api/export/work-orders.csv", "/api/export/complaints.csv"):
        r = client.get(path)
        assert r.status_code == 200
        assert "text/csv" in r.headers["content-type"]


def test_dashboard_stats():
    r = client.get("/api/dashboard/stats")
    assert r.status_code == 200
    body = r.json()
    for key in ("total_complaints", "open_work", "resolved", "by_class",
                "by_severity", "by_priority", "by_status", "by_department"):
        assert key in body


def test_departments():
    r = client.get("/api/departments")
    assert r.status_code == 200
    assert len(r.json()) == 6


def test_sklearn_ml_backend():
    """The trained RandomForest backend detects all classes when the model exists."""
    import os

    from app.ml.ml_detector import MODEL_PATH
    if not MODEL_PATH.exists():
        pytest.skip("ML model not trained (run scripts/train_classifier.py)")
    from app.ml.ml_detector import SklearnDetector
    from app.services.pipeline import load_image

    det = SklearnDetector()
    assert det.name == "sklearn"
    for stem in ("pothole", "garbage", "water_leakage", "blocked_drainage"):
        dets = det.detect(load_image((SAMPLES / f"{stem}.jpg").read_bytes()))
        assert dets, stem
        assert dets[0].class_name == stem, (stem, dets[:1])
    # clean road must not trigger anything
    assert det.detect(load_image((SAMPLES / "clean_road.jpg").read_bytes())) == []


import pytest  # noqa: E402
