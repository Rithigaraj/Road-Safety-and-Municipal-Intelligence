"""Department assignment: route each detection to the responsible department
with a workload-aware suggested SLA and queue position.
"""
from __future__ import annotations

from dataclasses import dataclass

from .classes import DEPARTMENTS, DEPARTMENT_IDS, PROBLEM_CLASSES, department_for_class


@dataclass
class Assignment:
    department_code: str
    department_name: str
    queue_position: int  # 1-based queue position for that department


def assign(class_name: str, open_count_by_department: dict[str, int]) -> Assignment:
    dept = department_for_class(class_name)
    open_count = open_count_by_department.get(dept, 0)
    return Assignment(
        department_code=dept,
        department_name=DEPARTMENTS[dept]["name"],
        queue_position=open_count + 1,
    )


def department_code_for_class(class_name: str) -> str:
    return PROBLEM_CLASSES[class_name]["department"]


def department_id_for_code(code: str) -> int:
    return DEPARTMENT_IDS[code]
