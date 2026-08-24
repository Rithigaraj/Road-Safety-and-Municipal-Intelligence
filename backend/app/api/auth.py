from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import User
from ..schemas import CreateUserIn, LoginIn, TokenOut, UserOut
from ..services.auth import create_token, hash_password, require_roles, verify_password

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/login", response_model=TokenOut)
def login(payload: LoginIn, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == payload.username.strip()).first()
    if not user or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    return TokenOut(
        access_token=create_token(user),
        role=user.role,
        username=user.username,
        department_code=user.department_code,
    )


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(require_roles("admin", "supervisor", "crew"))):
    return user


@router.get("/users", response_model=list[UserOut])
def list_users(_: User = Depends(require_roles("admin")), db: Session = Depends(get_db)):
    return db.query(User).order_by(User.id).all()


@router.post("/users", response_model=UserOut, status_code=201)
def create_user(payload: CreateUserIn,
                admin: User = Depends(require_roles("admin")),
                db: Session = Depends(get_db)):
    if payload.role not in {"admin", "supervisor", "crew"}:
        raise HTTPException(status_code=422, detail="role must be admin | supervisor | crew")
    if db.query(User).filter(User.username == payload.username.strip()).count():
        raise HTTPException(status_code=409, detail="username already exists")
    user = User(
        username=payload.username.strip(),
        password_hash=hash_password(payload.password),
        role=payload.role,
        department_code=payload.department_code,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user
