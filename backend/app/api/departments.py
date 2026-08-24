from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Department, Detection, WorkOrder
from ..schemas import DepartmentOut

router = APIRouter(prefix="/api/departments", tags=["departments"])


@router.get("", response_model=list[DepartmentOut])
def list_departments(db: Session = Depends(get_db)):
    depts = db.query(Department).order_by(Department.id).all()
    open_rows = (
        db.query(Detection.department_code, func.count(WorkOrder.id))
        .join(WorkOrder, WorkOrder.detection_id == Detection.id)
        .filter(WorkOrder.status != "resolved")
        .group_by(Detection.department_code)
        .all()
    )
    open_map = {code: cnt for code, cnt in open_rows}
    return [DepartmentOut(id=d.id, code=d.code, name=d.name, color=d.color,
                          open_work=open_map.get(d.code, 0)) for d in depts]
