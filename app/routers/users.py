from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.audit import record_audit, snapshot
from app.auth import get_current_editor, hash_api_key, require_admin
from app.database import get_db
from app.models import AuditAction, User
from app.schemas import UserCreate, UserPublic

router = APIRouter(prefix="/api/users", tags=["users"])


@router.get("/me", response_model=UserPublic)
def get_me(user: User = Depends(get_current_editor)) -> User:
    return user


@router.get("/editors")
def list_editors(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_editor),
) -> list[dict]:
    users = db.scalars(select(User).where(User.is_active.is_(True)).order_by(User.name)).all()
    return [{"id": user.id, "name": user.name, "role": user.role.value} for user in users]


@router.post("", response_model=UserPublic, status_code=status.HTTP_201_CREATED)
def create_user(
    payload: UserCreate,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
) -> User:
    existing = db.scalar(select(User).where(User.email == payload.email))
    if existing:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already exists.")
    user = User(
        name=payload.name,
        email=payload.email,
        role=payload.role,
        api_key_hash=hash_api_key(payload.api_key),
    )
    db.add(user)
    db.flush()
    record_audit(
        db,
        admin,
        AuditAction.create,
        "user",
        user.id,
        f"Created editor {user.name}",
        None,
        snapshot(user),
    )
    db.commit()
    db.refresh(user)
    return user
