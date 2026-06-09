from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import get_current_editor
from app.database import get_db
from app.models import EditHistory, User

router = APIRouter(prefix="/api/audit", tags=["audit"])


@router.get("")
def list_audit_log(
    limit: int = Query(default=50, ge=1, le=200),
    entity_type: str | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_editor),
) -> list[dict]:
    query = select(EditHistory)
    if entity_type:
        query = query.where(EditHistory.entity_type == entity_type)
    entries = db.scalars(query.order_by(EditHistory.created_at.desc()).limit(limit)).all()
    return [
        {
            "id": entry.id,
            "editor_name": entry.editor_name,
            "action": entry.action.value,
            "entity_type": entry.entity_type,
            "entity_id": entry.entity_id,
            "summary": entry.summary,
            "created_at": entry.created_at.isoformat(),
        }
        for entry in entries
    ]
