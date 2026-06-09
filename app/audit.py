from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import inspect
from sqlalchemy.orm import Session

from app.models import AuditAction, EditHistory, User


def _jsonable(value: Any) -> Any:
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, dict):
        return {key: _jsonable(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_jsonable(item) for item in value]
    return value


def snapshot(model: Any | None) -> dict[str, Any] | None:
    if model is None:
        return None
    mapper = inspect(model).mapper
    return _jsonable({column.key: getattr(model, column.key) for column in mapper.columns})


def record_audit(
    db: Session,
    user: User,
    action: AuditAction,
    entity_type: str,
    entity_id: int | None,
    summary: str,
    before: dict[str, Any] | None,
    after: dict[str, Any] | None,
) -> EditHistory:
    entry = EditHistory(
        user_id=user.id,
        editor_name=user.name,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        summary=summary,
        before=_jsonable(before),
        after=_jsonable(after),
    )
    db.add(entry)
    return entry
