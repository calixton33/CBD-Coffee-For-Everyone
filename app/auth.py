from __future__ import annotations

import hashlib

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models import User, UserRole


def hash_api_key(api_key: str) -> str:
    raw = f"{settings.secret_key}:{api_key}".encode("utf-8")
    return hashlib.sha256(raw).hexdigest()
 

def get_current_editor(
    x_editor_key: str | None = Header(default=None, alias="X-Editor-Key"),
    db: Session = Depends(get_db),
) -> User:
    if not x_editor_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Editor key required.",
        )

    user = db.scalar(
        select(User).where(
            User.api_key_hash == hash_api_key(x_editor_key),
            User.is_active.is_(True),
        )
    )
    if not user:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid or inactive editor key.",
        )
    if user.role not in {UserRole.admin, UserRole.editor}:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This user cannot make edits.",
        )
    return user


def require_admin(user: User = Depends(get_current_editor)) -> User:
    if user.role != UserRole.admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin required.")
    return user
