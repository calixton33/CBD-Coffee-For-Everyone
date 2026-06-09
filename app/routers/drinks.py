from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.audit import record_audit, snapshot
from app.auth import get_current_editor
from app.database import get_db
from app.models import AuditAction, Drink, User
from app.schemas import DrinkCreate, DrinkUpdate
from app.services.menus import get_drink_or_404

router = APIRouter(prefix="/api/drinks", tags=["drinks"])


def serialize_drink(drink: Drink) -> dict:
    return {
        "id": drink.id,
        "name": drink.name,
        "drink_type": drink.drink_type,
        "default_size": drink.default_size,
        "description": drink.description,
        "is_active": drink.is_active,
    }


@router.get("")
def list_drinks(include_inactive: bool = False, db: Session = Depends(get_db)) -> list[dict]:
    query = select(Drink)
    if not include_inactive:
        query = query.where(Drink.is_active.is_(True))
    drinks = db.scalars(query.order_by(Drink.drink_type, Drink.name)).all()
    return [serialize_drink(drink) for drink in drinks]


@router.post("", status_code=status.HTTP_201_CREATED)
def create_drink(
    payload: DrinkCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_editor),
) -> dict:
    duplicate = db.scalar(
        select(Drink).where(
            Drink.name == payload.name,
            Drink.drink_type == payload.drink_type,
        )
    )
    if duplicate:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A drink with this name and type already exists.",
        )
    drink = Drink(**payload.model_dump())
    db.add(drink)
    db.flush()
    record_audit(
        db,
        user,
        AuditAction.create,
        "drink",
        drink.id,
        f"Created drink {drink.name}",
        None,
        snapshot(drink),
    )
    db.commit()
    db.refresh(drink)
    return serialize_drink(drink)


@router.put("/{drink_id}")
def update_drink(
    drink_id: int,
    payload: DrinkUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_editor),
) -> dict:
    drink = get_drink_or_404(db, drink_id)
    before = snapshot(drink)
    data = payload.model_dump(exclude_unset=True)
    for key, value in data.items():
        setattr(drink, key, value)
    db.flush()
    record_audit(
        db,
        user,
        AuditAction.update,
        "drink",
        drink.id,
        f"Updated drink {drink.name}",
        before,
        snapshot(drink),
    )
    db.commit()
    db.refresh(drink)
    return serialize_drink(drink)


@router.delete("/{drink_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_drink(
    drink_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_editor),
) -> None:
    drink = get_drink_or_404(db, drink_id)
    before = snapshot(drink)
    drink.is_active = False
    db.flush()
    record_audit(
        db,
        user,
        AuditAction.delete,
        "drink",
        drink.id,
        f"Archived drink {drink.name}",
        before,
        snapshot(drink),
    )
    db.commit()
