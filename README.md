# AI-Powered Road Safety & Municipal Intelligence Platform

Cities receive thousands of complaints about potholes, damaged roads, broken
streetlights, garbage overflow, water leakage, illegal dumping, damaged traffic
signs and blocked drainage. This platform automates the whole pipeline:

```
Citizen / CCTV / Dashcam
        ↓  image / video frame
   Computer vision
        ↓
   Infrastructure problem detected
        ↓
   Severity model  ──  GPS / location
        ↓
   Priority prediction (P1–P4)
        ↓
   Department assignment  (auto-routing)
        ↓
   Municipal dashboard (work tracking)
        ↓
   AI verification of completed fixes
```

## What is included

| Layer | Technology | Files |
| --- | --- | --- |
| Vision detection | Self-contained heuristic detector + optional Ultralytics YOLO | `backend/app/ml/detector.py` |
| Severity model | Confidence + visual-signal fusion | `backend/app/ml/severity.py` |
| Priority prediction | class-risk · severity · location · recency → P1–P4 + SLA | `backend/app/ml/priority.py` |
| Department assignment | class → department + queue position | `backend/app/ml/assignment.py` |
| AI verification | compares resolution photo against original detection | `backend/app/services/verification.py` |
| REST API | FastAPI | `backend/app/api/*.py` |
| Storage | SQLite + SQLAlchemy | `backend/app/models.py` |
| Dashboard | React (Vite) + recharts + Leaflet map | `dashboard/` |

Seven problem classes are supported:

| Class | Department |
| --- | --- |
| `pothole`, `road_crack` | Road Maintenance |
| `broken_streetlight` | Street Lighting |
| `garbage` | Waste Management |
| `water_leakage` | Water Supply |
| `blocked_drainage` | Drainage & Sewage |
| `damaged_traffic_sign` | Traffic & Signage |

## Quick start

### 1. Backend

```bash
cd backend
pip install -r requirements.txt
python -m scripts.generate_samples     # optional: recreate synthetic sample images
python -m scripts.seed_db              # creates the demo dataset (9 complaints)
python run.py                          # serves API on http://localhost:8000
```

The API docs are available at http://localhost:8000/docs.

### 2. Dashboard (optional — the built bundle is served automatically)

```bash
cd dashboard
npm install
npm run build     # outputs dist/, which FastAPI serves at /
# or for development with hot reload:
npm run dev       # http://localhost:5173, proxies /api to :8000
```

### 3. Tests

```bash
cd backend
python -m pytest tests -q
```

## Detection backends

The default `heuristic` backend is fully self-contained (numpy + Pillow) and
needs no model downloads — it is intentionally explainable and works on the
bundled synthetic samples so the demo runs offline.

For production, switch to a real object-detection model:

```bash
pip install ultralytics
$env:DETECTOR_BACKEND = "yolo"
$env:YOLO_MODEL_PATH  = "yolov8n.pt"
python run.py
```

`DETECTOR_BACKEND=auto` prefers YOLO when `ultralytics` is installed and falls
back to the heuristic backend otherwise.

## API overview

| Method | Endpoint | Description |
| --- | --- | --- |
| POST | `/api/complaints/analyze` | Run analysis on an image without saving |
| POST | `/api/complaints` | Submit a complaint (multipart image + fields) → full pipeline |
| GET | `/api/complaints` · `/api/complaints/{id}` | List / get complaints |
| GET | `/api/work-orders` | List work orders (optional `?status=`) |
| PATCH | `/api/work-orders/{id}` | Update status / assignee / notes |
| POST | `/api/work-orders/{id}/verify` | Upload resolution photo → AI verification |
| GET | `/api/departments` | Departments with open-work counts |
| GET | `/api/dashboard/stats` | Aggregated dashboard statistics |
| GET | `/api/reports/heatmap` | Geolocated incidents for the map |
| GET | `/api/health` | Health check + active detector backend |

## Project layout

```
backend/
  app/
    main.py              # FastAPI app + lifespan + static mounts
    config.py            # paths, backend selection
    database.py          # SQLAlchemy engine/session
    models.py            # Complaint, Detection, WorkOrder, Department
    schemas.py           # Pydantic response models
    api/                 # complaints, work-orders, departments, dashboard
    services/            # pipeline (orchestration), verification
    ml/                  # classes, detector, severity, priority, assignment
  scripts/
    generate_samples.py  # synthetic images for all 7 classes
    seed_db.py           # demo dataset through the full pipeline
  data/
    samples/ uploads/ road_safety.db
  tests/
    test_api.py
dashboard/
  src/                   # React app (stats, map, charts, queue, work board)
  dist/                  # build output, served by FastAPI at /
```

## How the priority score works

```
priority = 0.30 * class_risk        (potholes > water leaks > cracks > …)
         + 0.38 * severity_score    (visual severity model)
         + 0.20 * location          (city core / schools / hospitals zone)
         + 0.12 * recency           (decays over one week)
→ bucketed into P1 (fix within 24h) … P4 (fix within 7 days)
```
