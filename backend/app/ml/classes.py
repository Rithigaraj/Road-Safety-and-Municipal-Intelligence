"""Known infrastructure problem classes, their owning departments and priority weights.

These constants drive the whole pipeline: detection -> severity -> priority -> assignment.
"""

PROBLEM_CLASSES = {
    "pothole": {
        "label": "Pothole",
        "department": "road_maintenance",
        "base_priority": 0.75,  # high because it directly causes accidents
    },
    "road_crack": {
        "label": "Road crack",
        "department": "road_maintenance",
        "base_priority": 0.45,
    },
    "garbage": {
        "label": "Garbage / illegal dumping",
        "department": "waste_management",
        "base_priority": 0.40,
    },
    "broken_streetlight": {
        "label": "Broken streetlight",
        "department": "street_lighting",
        "base_priority": 0.35,
    },
    "water_leakage": {
        "label": "Water leakage",
        "department": "water_supply",
        "base_priority": 0.65,
    },
    "damaged_traffic_sign": {
        "label": "Damaged traffic sign",
        "department": "traffic_signage",
        "base_priority": 0.55,
    },
    "blocked_drainage": {
        "label": "Blocked drainage",
        "department": "drainage",
        "base_priority": 0.60,
    },
}

DETECTABLE_CLASSES = sorted(PROBLEM_CLASSES.keys())

DEPARTMENTS = {
    "road_maintenance": {"name": "Road Maintenance", "color": "#ef4444"},
    "street_lighting": {"name": "Street Lighting", "color": "#f59e0b"},
    "waste_management": {"name": "Waste Management", "color": "#10b981"},
    "water_supply": {"name": "Water Supply", "color": "#3b82f6"},
    "drainage": {"name": "Drainage & Sewage", "color": "#06b6d4"},
    "traffic_signage": {"name": "Traffic & Signage", "color": "#8b5cf6"},
}

DEPARTMENT_IDS = {code: i + 1 for i, code in enumerate(sorted(DEPARTMENTS))}

# Coco class names that map to our own problem classes (used by the YOLO backend).
YOLO_CLASS_MAP = {
    "pothole": "pothole",
    "car": None,
    "traffic light": "damaged_traffic_sign",
}

SEVERITY_ORDER = {"low": 0, "medium": 1, "high": 2, "critical": 3}

PRIORITY_LEVELS = {
    "P1": (0.75, 1.0),  # fix within hours
    "P2": (0.55, 0.75),  # fix within 24h
    "P3": (0.35, 0.55),  # fix within 3 days
    "P4": (0.0, 0.35),   # fix within 7 days
}

SLA_HOURS = {"P1": 24, "P2": 48, "P3": 72, "P4": 168}


def department_for_class(class_name: str) -> str:
    return PROBLEM_CLASSES[class_name]["department"]


def priority_level_for_score(score: float) -> str:
    for level, (lo, hi) in PRIORITY_LEVELS.items():
        if lo <= score < hi:
            return level
    return "P4"
