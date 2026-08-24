from __future__ import annotations

import secrets
from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship

from .database import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def new_tracking_code() -> str:
    return "RSM-" + secrets.token_hex(4).upper()


class Complaint(Base):
    __tablename__ = "complaints"

    id = Column(Integer, primary_key=True, index=True)
    tracking_code = Column(String(16), unique=True, index=True, default=new_tracking_code)
    source = Column(String(20), default="citizen")  # citizen | cctv | dashcam | telegram
    description = Column(Text, default="")
    lat = Column(Float, nullable=True)
    lon = Column(Float, nullable=True)
    address = Column(String(255), nullable=True)
    image_path = Column(String(512), nullable=True)
    created_at = Column(DateTime, default=utcnow, index=True)

    detections = relationship("Detection", back_populates="complaint",
                              cascade="all, delete-orphan", order_by="Detection.confidence.desc()")


class Detection(Base):
    __tablename__ = "detections"

    id = Column(Integer, primary_key=True, index=True)
    complaint_id = Column(Integer, ForeignKey("complaints.id"), index=True)
    class_name = Column(String(64), index=True)
    confidence = Column(Float)
    bbox_x1 = Column(Integer)
    bbox_y1 = Column(Integer)
    bbox_x2 = Column(Integer)
    bbox_y2 = Column(Integer)
    severity = Column(String(16))      # low | medium | high | critical
    severity_score = Column(Float)
    priority_score = Column(Float)
    priority_level = Column(String(4))  # P1..P4
    sla_hours = Column(Integer)
    department_code = Column(String(32), index=True)
    queue_position = Column(Integer, default=1)
    size_estimate_cm = Column(Float, nullable=True)     # approx real-world width
    duplicate_of_id = Column(Integer, ForeignKey("detections.id"), nullable=True)
    report_count = Column(Integer, default=1)           # how many reports map to this issue

    complaint = relationship("Complaint", back_populates="detections")
    work_orders = relationship("WorkOrder", back_populates="detection",
                               cascade="all, delete-orphan")


class WorkOrder(Base):
    __tablename__ = "work_orders"

    id = Column(Integer, primary_key=True, index=True)
    detection_id = Column(Integer, ForeignKey("detections.id"), index=True)
    status = Column(String(24), default="assigned")  # assigned|in_progress|resolved
    assignee = Column(String(64), nullable=True)
    notes = Column(Text, default="")
    created_at = Column(DateTime, default=utcnow)
    assigned_at = Column(DateTime, nullable=True)
    started_at = Column(DateTime, nullable=True)
    resolved_at = Column(DateTime, nullable=True)
    verification_status = Column(String(24), nullable=True)  # pending|verified|failed
    verification_confidence = Column(Float, nullable=True)
    verification_note = Column(Text, nullable=True)
    resolution_image_path = Column(String(512), nullable=True)
    estimated_cost = Column(Float, nullable=True)
    actual_cost = Column(Float, nullable=True)
    escalated_at = Column(DateTime, nullable=True)
    escalation_note = Column(Text, nullable=True)

    detection = relationship("Detection", back_populates="work_orders")


class Department(Base):
    __tablename__ = "departments"

    id = Column(Integer, primary_key=True)
    code = Column(String(32), unique=True, index=True)
    name = Column(String(64))
    color = Column(String(16))


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(64), unique=True, index=True)
    password_hash = Column(String(256))
    role = Column(String(24), default="crew")  # admin | supervisor | crew
    department_code = Column(String(32), nullable=True)


class Notification(Base):
    __tablename__ = "notifications"

    id = Column(Integer, primary_key=True, index=True)
    type = Column(String(32))          # new_complaint | sla_breach | escalation | verification
    title = Column(String(200))
    body = Column(Text, default="")
    ref_type = Column(String(32), nullable=True)
    ref_id = Column(Integer, nullable=True)
    read = Column(Boolean, default=False, index=True)
    created_at = Column(DateTime, default=utcnow, index=True)
