import asyncio
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from .api import auth, complaints, dashboard, departments, dispatch, exports, \
    notifications, reports, work_orders
from .config import DATA_DIR
from .database import Base, SessionLocal, engine
from .ml.classes import DEPARTMENTS, DEPARTMENT_IDS
from .models import Department
from .services.auth import seed_default_users
from .services.ws import hub


async def _sla_watchdog(interval_seconds: int = 600) -> None:
    """Periodically flag SLA breaches so notifications fire even on quiet days."""
    from .services.sla import breach_scan
    while True:
        await asyncio.sleep(interval_seconds)
        db = SessionLocal()
        try:
            breach_scan(db)
        except Exception as exc:
            print(f"[sla-watchdog] {exc}")
        finally:
            db.close()


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        existing = {d.code for d in db.query(Department).all()}
        for code, info in DEPARTMENTS.items():
            if code not in existing:
                db.add(Department(id=DEPARTMENT_IDS[code], code=code,
                                  name=info["name"], color=info["color"]))
        db.commit()
        seed_default_users(db)
    finally:
        db.close()

    hub.loop = asyncio.get_running_loop()
    watchdog = asyncio.create_task(_sla_watchdog())
    yield
    watchdog.cancel()


app = FastAPI(
    title="Road Safety & Municipal Intelligence Platform",
    version="0.2.0",
    description=(
        "AI pipeline: image -> infrastructure problem detection -> severity -> "
        "priority -> department assignment -> work tracking -> AI verification. "
        "Plus duplicate clustering, SLA escalation, crew routing, analytics and "
        "live websocket updates."
    ),
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

for r in (complaints.router, work_orders.router, departments.router,
          dashboard.router, reports.router, dispatch.router,
          notifications.router, exports.router, auth.router):
    app.include_router(r)


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """Live event stream for the ops dashboard."""
    await hub.connect(websocket)
    try:
        while True:
            await websocket.receive_text()  # keepalive pings from clients
    except WebSocketDisconnect:
        hub.disconnect(websocket)


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok", "detector_backend": _backend_name()}


def _backend_name() -> str:
    from .ml.detector import get_detector
    try:
        return get_detector().name
    except Exception:
        return "unknown"


# Static assets (uploaded images) and the built React dashboard.
app.mount("/uploads", StaticFiles(directory=DATA_DIR / "uploads"), name="uploads")

_dashboard_dist = Path(__file__).resolve().parent.parent.parent / "dashboard" / "dist"
if _dashboard_dist.exists():
    app.mount("/", StaticFiles(directory=_dashboard_dist, html=True), name="dashboard")
