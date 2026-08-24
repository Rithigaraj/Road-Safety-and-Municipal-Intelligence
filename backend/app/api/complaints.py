import io
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from PIL import Image
from sqlalchemy.orm import Session

from ..config import UPLOAD_DIR
from ..database import get_db
from ..models import Complaint, Detection
from ..schemas import AnalyzeResult, ComplaintOut, DetectionOut
from ..services import pipeline

router = APIRouter(prefix="/api/complaints", tags=["complaints"])


def _detection_out(d: Detection) -> DetectionOut:
    return DetectionOut(
        id=d.id,
        class_name=d.class_name,
        confidence=round(d.confidence, 3),
        bbox=(d.bbox_x1, d.bbox_y1, d.bbox_x2, d.bbox_y2),
        severity=d.severity,
        severity_score=round(d.severity_score or 0.0, 3),
        priority_score=round(d.priority_score or 0.0, 3),
        priority_level=d.priority_level or "P4",
        sla_hours=d.sla_hours or 168,
        department_code=d.department_code,
        queue_position=d.queue_position or 1,
        size_estimate_cm=d.size_estimate_cm,
        duplicate_of_id=d.duplicate_of_id,
        report_count=d.report_count or 1,
        is_duplicate=d.duplicate_of_id is not None,
    )


def _complaint_out(c: Complaint) -> ComplaintOut:
    return ComplaintOut(
        id=c.id,
        tracking_code=c.tracking_code,
        source=c.source,
        description=c.description,
        lat=c.lat,
        lon=c.lon,
        address=c.address,
        image_path=c.image_path,
        created_at=c.created_at,
        detections=[_detection_out(d) for d in c.detections],
    )


def _save_bytes(data: bytes, suffix: str = ".jpg") -> str:
    name = f"{uuid.uuid4().hex}{suffix}"
    path = UPLOAD_DIR / name
    path.write_bytes(data)
    return str(path.relative_to(Path(__file__).resolve().parent.parent.parent))


def _analysis_payload(results) -> AnalyzeResult:
    detections = [
        DetectionOut(
            class_name=r.detection.class_name,
            confidence=round(r.detection.confidence, 3),
            bbox=r.detection.bbox,
            severity=r.severity_label,
            severity_score=r.severity_score,
            priority_score=r.priority_score,
            priority_level=r.priority_level,
            sla_hours=r.sla_hours,
            department_code=r.department_code,
            queue_position=1,
            size_estimate_cm=r.size_estimate_cm,
        )
        for r in results
    ]
    top = results[0] if results else None
    return AnalyzeResult(
        detections=detections,
        top_class=top.detection.class_name if top else None,
        top_severity=top.severity_label if top else None,
        top_priority_level=top.priority_level if top else None,
        top_department=top.department_code if top else None,
    )


@router.post("/analyze", response_model=AnalyzeResult)
async def analyze_image(
    lat: float | None = Form(None),
    lon: float | None = Form(None),
    file: UploadFile = File(...),
):
    """Dry-run analysis: what would we detect, how bad is it, who gets it?"""
    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="Empty image uploaded.")
    results = pipeline.analyze(data, lat=lat, lon=lon)
    return _analysis_payload(results)


@router.post("", response_model=ComplaintOut, status_code=201)
async def create_complaint(
    source: str = Form("citizen"),
    description: str = Form(""),
    lat: float | None = Form(None),
    lon: float | None = Form(None),
    address: str | None = Form(None),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    """File a complaint. lat/lon are optional - JPEG EXIF GPS is used as fallback."""
    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="Empty image uploaded.")
    image_path = _save_bytes(data, Path(file.filename or "upload.jpg").suffix or ".jpg")

    complaint = Complaint(
        source=source,
        description=description,
        lat=lat,
        lon=lon,
        address=address,
        image_path=image_path,
    )
    db.add(complaint)
    db.flush()
    try:
        pipeline.process_complaint(db, complaint, data)
    except Exception as exc:  # keep the complaint even if analysis fails
        db.rollback()
        db.add(complaint)
        db.commit()
        raise HTTPException(status_code=422, detail=f"Analysis failed: {exc}")
    db.refresh(complaint)
    return _complaint_out(complaint)


@router.post("/video", response_model=list[ComplaintOut], status_code=201)
async def create_from_video(
    source: str = Form("cctv"),
    lat: float | None = Form(None),
    lon: float | None = Form(None),
    address: str | None = Form(None),
    frames_to_sample: int = Form(8),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    """Ingest CCTV/dashcam footage: sample frames, analyse each, then group the
    findings into one complaint per distinct problem class."""
    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="Empty video uploaded.")

    frames = _extract_frames(data, max(1, min(frames_to_sample, 30)))
    if not frames:
        raise HTTPException(
            status_code=400,
            detail=("Could not decode video. Video ingestion requires OpenCV: "
                    "pip install opencv-python-headless"),
        )

    best: dict[str, pipeline.AnalyzedDetection] = {}
    for frame in frames:
        buf = io.BytesIO()
        Image.fromarray(frame).save(buf, format="JPEG", quality=90)
        for r in pipeline.analyze(buf.getvalue(), lat=lat, lon=lon):
            known = best.get(r.detection.class_name)
            if known is None or r.detection.confidence > known.detection.confidence:
                best[r.detection.class_name] = r

    if not best:
        raise HTTPException(status_code=422,
                            detail="No infrastructure problems found in any sampled frame.")

    first_frame = frames[0]
    buf = io.BytesIO()
    Image.fromarray(first_frame).save(buf, format="JPEG", quality=90)
    frame_bytes = buf.getvalue()

    created: list[ComplaintOut] = []
    for cls, r in best.items():
        complaint = Complaint(
            source=source,
            description=f"Auto-detected from video feed: {cls}",
            lat=lat, lon=lon, address=address,
            image_path=_save_bytes(frame_bytes),
        )
        db.add(complaint)
        db.flush()
        try:
            pipeline.process_complaint(db, complaint, frame_bytes)
        except Exception:
            db.rollback()
            continue
        db.refresh(complaint)
        created.append(_complaint_out(complaint))

    if not created:
        raise HTTPException(status_code=422, detail="Video analysis failed; nothing recorded.")
    return created


def _extract_frames(data: bytes, wanted: int) -> list[Image.Image]:
    """Evenly sample frames from an uploaded video. Requires opencv-python."""
    try:
        import cv2
        import numpy as np
    except ImportError:
        return []
    tmp_path = UPLOAD_DIR / f"tmp_{uuid.uuid4().hex}.mp4"
    tmp_path.write_bytes(data)
    frames: list[Image.Image] = []
    try:
        cap = cv2.VideoCapture(str(tmp_path))
        total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        if total <= 0:
            return []
        step = max(total // wanted, 1)
        for idx in range(0, total, step)[:wanted]:
            cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
            ok, frame = cap.read()
            if ok:
                img = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
                img.thumbnail((1024, 1024))
                frames.append(img)
        cap.release()
    finally:
        tmp_path.unlink(missing_ok=True)
    return frames


@router.get("", response_model=list[ComplaintOut])
def list_complaints(db: Session = Depends(get_db)):
    return [_complaint_out(c) for c in db.query(Complaint).order_by(Complaint.created_at.desc()).all()]


@router.get("/track/{code}", response_model=ComplaintOut)
def track_by_code(code: str, db: Session = Depends(get_db)):
    """Public status lookup by tracking code (no auth needed)."""
    complaint = db.query(Complaint).filter(Complaint.tracking_code == code.strip().upper()).first()
    if not complaint:
        raise HTTPException(status_code=404, detail="Unknown tracking code")
    return _complaint_out(complaint)


@router.get("/{complaint_id}", response_model=ComplaintOut)
def get_complaint(complaint_id: int, db: Session = Depends(get_db)):
    complaint = db.get(Complaint, complaint_id)
    if not complaint:
        raise HTTPException(status_code=404, detail="Complaint not found")
    return _complaint_out(complaint)
