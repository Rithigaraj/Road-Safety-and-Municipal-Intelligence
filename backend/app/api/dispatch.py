"""Crew dispatch: an optimised visit route for a department's open work orders."""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import User
from ..services.auth import require_roles
from ..services.dispatch import build_route

router = APIRouter(prefix="/api/dispatch", tags=["dispatch"])


@router.get("/route")
def dispatch_route(
    department: str | None = Query(None, description="filter by department code"),
    user: User = Depends(require_roles("admin", "supervisor", "crew")),
    db: Session = Depends(get_db),
):
    """Greedy nearest-neighbour + 2-opt route over open jobs, depot -> ... -> last."""
    return build_route(db, department_code=department)
