from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class DetectionOut(BaseModel):
    id: int | None = None
    class_name: str
    confidence: float
    bbox: tuple[int, int, int, int]
    severity: str
    severity_score: float
    priority_score: float
    priority_level: str
    sla_hours: int
    department_code: str
    queue_position: int
    size_estimate_cm: float | None = None
    duplicate_of_id: int | None = None
    report_count: int = 1
    is_duplicate: bool = False

    model_config = {"from_attributes": True}


class ComplaintOut(BaseModel):
    id: int
    tracking_code: str | None = None
    source: str
    description: str
    lat: float | None
    lon: float | None
    address: str | None
    image_path: str | None
    created_at: datetime
    detections: list[DetectionOut] = []

    model_config = {"from_attributes": True}


class WorkOrderUpdate(BaseModel):
    status: str | None = Field(None, pattern="^(assigned|in_progress|resolved)$")
    assignee: str | None = None
    notes: str | None = None
    estimated_cost: float | None = Field(None, ge=0)
    actual_cost: float | None = Field(None, ge=0)


class WorkOrderOut(BaseModel):
    id: int
    status: str
    assignee: str | None
    notes: str
    created_at: datetime
    assigned_at: datetime | None
    started_at: datetime | None
    resolved_at: datetime | None
    verification_status: str | None
    verification_confidence: float | None
    verification_note: str | None
    estimated_cost: float | None = None
    actual_cost: float | None = None
    escalated_at: datetime | None = None
    escalation_note: str | None = None
    sla_hours: int | None = None
    sla_remaining_hours: float | None = None
    sla_breached: bool = False
    detection: DetectionOut | None = None
    complaint: ComplaintOut | None = None

    model_config = {"from_attributes": True}


class DepartmentOut(BaseModel):
    id: int
    code: str
    name: str
    color: str
    open_work: int = 0

    model_config = {"from_attributes": True}


class AnalyzeResult(BaseModel):
    detections: list[DetectionOut]
    top_class: str | None
    top_severity: str | None
    top_priority_level: str | None
    top_department: str | None


# ------------------------------------------------------------------- auth

class LoginIn(BaseModel):
    username: str
    password: str


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    role: str
    username: str
    department_code: str | None = None


class UserOut(BaseModel):
    id: int
    username: str
    role: str
    department_code: str | None = None

    model_config = {"from_attributes": True}


class CreateUserIn(BaseModel):
    username: str
    password: str
    role: str = "crew"
    department_code: str | None = None


# ---------------------------------------------------------- notifications

class NotificationOut(BaseModel):
    id: int
    type: str
    title: str
    body: str
    ref_type: str | None = None
    ref_id: int | None = None
    read: bool
    created_at: datetime

    model_config = {"from_attributes": True}
