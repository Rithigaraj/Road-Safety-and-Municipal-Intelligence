"""Authentication: PBKDF2 password hashing + minimal HS256 JWT + role guards.

Deliberately dependency-free (hashlib/hmac from the stdlib) so the MVP has no
extra install requirements. Swap for `python-jose`/`passlib` in production.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import User

SECRET_KEY = os.getenv("JWT_SECRET", "dev-secret-change-me")
TOKEN_TTL_HOURS = int(os.getenv("JWT_TTL_HOURS", "12"))

_bearer = HTTPBearer(auto_error=False)

ROLES = ("admin", "supervisor", "crew")


# ---------------------------------------------------------------- passwords

def hash_password(password: str) -> str:
    salt = os.urandom(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 120_000)
    return f"pbkdf2${salt.hex()}${dk.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        _, salt_hex, dk_hex = stored.split("$")
        dk = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt_hex), 120_000)
        return hmac.compare_digest(dk.hex(), dk_hex)
    except Exception:
        return False


# ---------------------------------------------------------------- JWT (HS256)

def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _unb64(data: str) -> bytes:
    return base64.urlsafe_b64decode(data + "=" * (-len(data) % 4))


def create_token(user: User) -> str:
    header = _b64(json.dumps({"alg": "HS256", "typ": "JWT"}).encode())
    payload = _b64(json.dumps({
        "sub": user.username,
        "role": user.role,
        "dept": user.department_code,
        "exp": int(time.time()) + TOKEN_TTL_HOURS * 3600,
    }).encode())
    signing = f"{header}.{payload}".encode()
    sig = _b64(hmac.new(SECRET_KEY.encode(), signing, hashlib.sha256).digest())
    return f"{header}.{payload}.{sig}"


def decode_token(token: str) -> dict | None:
    try:
        header, payload, sig = token.split(".")
        expected = _b64(hmac.new(SECRET_KEY.encode(), f"{header}.{payload}".encode(), hashlib.sha256).digest())
        if not hmac.compare_digest(sig, expected):
            return None
        claims = json.loads(_unb64(payload))
        if int(claims.get("exp", 0)) < time.time():
            return None
        return claims
    except Exception:
        return None


# ---------------------------------------------------------------- FastAPI deps

def optional_user(
    creds: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: Session = Depends(get_db),
) -> User | None:
    if creds is None:
        return None
    claims = decode_token(creds.credentials)
    if not claims:
        return None
    return db.query(User).filter(User.username == claims.get("sub")).first()


def require_roles(*roles: str):
    def dep(user: User | None = Depends(optional_user)) -> User:
        if user is None:
            raise HTTPException(status_code=401, detail="Login required")
        if roles and user.role not in roles:
            raise HTTPException(status_code=403, detail=f"Requires role: {' / '.join(roles)}")
        return user
    return dep


require_staff = require_roles("admin", "supervisor", "crew")
require_admin = require_roles("admin")


def seed_default_users(db: Session) -> None:
    """Create default accounts on first run so the demo is usable immediately."""
    if db.query(User).count():
        return
    defaults = [
        ("admin", "admin123", "admin", None),
        ("supervisor", "supervisor123", "supervisor", None),
        ("crew", "crew123", "crew", "road_maintenance"),
    ]
    for username, password, role, dept in defaults:
        db.add(User(username=username, password_hash=hash_password(password), role=role,
                    department_code=dept))
    db.commit()
