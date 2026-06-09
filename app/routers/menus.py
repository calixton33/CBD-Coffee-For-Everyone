from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload, selectinload

from app.audit import record_audit, snapshot
from app.auth import get_current_editor
from app.database import get_db
from app.models import AuditAction, MenuItem, MenuScope, Price, User, utc_now
from app.schemas import MenuItemUpdate
from app.services.menus import (
    current_price,
    get_menu_item_or_404,
    serialize_menu_item,
    serialize_price,
    set_current_price,
)

router = APIRouter(prefix="/api", tags=["menus"])


@router.get("/menu-items/{menu_item_id}/prices")
def list_price_history(menu_item_id: int, db: Session = Depends(get_db)) -> list[dict]:
    item = get_menu_item_or_404(db, menu_item_id)
    return [
        {
            **serialize_price(price),
            "effective_to": price.effective_to.isoformat() if price.effective_to else None,
        }
        for price in item.prices
    ]


@router.put("/menu-items/{menu_item_id}")
def update_menu_item(
    menu_item_id: int,
    payload: MenuItemUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_editor),
) -> dict:
    item = get_menu_item_or_404(db, menu_item_id)
    before = snapshot(item)
    before_price = snapshot(current_price(item))
    data = payload.model_dump(exclude_unset=True)

    if "notes" in data:
        item.notes = data["notes"]
    if "is_available" in data:
        item.is_available = data["is_available"]

    amount = data.get("amount")
    currency = data.get("currency")
    size_label = data.get("size_label") if "size_label" in data else None
    if amount is not None:
        existing_price = current_price(item)
        set_current_price(
            db,
            item,
            amount=amount,
            currency=currency or (existing_price.currency if existing_price else "SGD"),
            size_label=size_label
            if "size_label" in data
            else (existing_price.size_label if existing_price else None),
            user=user,
            is_override=item.menu.scope == MenuScope.outlet,
        )

    db.flush()
    record_audit(
        db,
        user,
        AuditAction.update,
        "menu_item",
        item.id,
        f"Updated {item.drink.name} on {item.menu.name}",
        {"item": before, "price": before_price},
        {"item": snapshot(item), "price": snapshot(current_price(item))},
    )
    db.commit()
    return serialize_menu_item(get_menu_item_or_404(db, item.id))


@router.delete("/menu-items/{menu_item_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_menu_item(
    menu_item_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_editor),
) -> None:
    item = get_menu_item_or_404(db, menu_item_id)
    before = snapshot(item)
    item.is_available = False
    db.flush()
    record_audit(
        db,
        user,
        AuditAction.delete,
        "menu_item",
        item.id,
        f"Archived {item.drink.name} on {item.menu.name}",
        before,
        snapshot(item),
    )
    db.commit()


@router.delete("/prices/{price_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_price(
    price_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_editor),
) -> None:
    price = db.scalar(
        select(Price)
        .options(joinedload(Price.menu_item).joinedload(MenuItem.drink))
        .where(Price.id == price_id)
    )
    if not price:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Price not found.")
    before = snapshot(price)
    if price.effective_to is None:
        price.effective_to = utc_now()
    db.flush()
    record_audit(
        db,
        user,
        AuditAction.delete,
        "price",
        price.id,
        f"Archived price for {price.menu_item.drink.name}",
        before,
        snapshot(price),
    )
    db.commit()
