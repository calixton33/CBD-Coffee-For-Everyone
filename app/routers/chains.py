from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.audit import record_audit, snapshot
from app.auth import get_current_editor
from app.database import get_db
from app.models import AuditAction, Chain, Menu, MenuItem, MenuScope, User
from app.schemas import (
    ChainCreate,
    ChainUpdate,
    DuplicateMenuRequest,
    MenuItemCreate,
    MenuItemUpdate,
    SyncTemplateRequest,
)
from app.services.menus import (
    add_or_update_menu_item,
    copy_menu_items,
    current_price,
    get_chain_or_404,
    get_drink_or_404,
    get_menu_item_or_404,
    get_or_create_chain_template_menu,
    get_or_create_outlet_menu,
    get_shop_or_404,
    serialize_chain,
    serialize_menu_item,
    slugify,
    sync_template_to_outlets,
    unique_slug,
)

router = APIRouter(prefix="/api/chains", tags=["chains"])


@router.get("")
def list_chains(db: Session = Depends(get_db)) -> list[dict]:
    chains = db.scalars(
        select(Chain)
        .options(
            selectinload(Chain.shops),
            selectinload(Chain.menus).selectinload(Menu.items).selectinload(MenuItem.drink),
            selectinload(Chain.menus).selectinload(Menu.items).selectinload(MenuItem.prices),
        )
        .order_by(Chain.name)
    ).all()
    return [serialize_chain(chain) for chain in chains]


@router.get("/{chain_id}")
def get_chain(chain_id: int, db: Session = Depends(get_db)) -> dict:
    return serialize_chain(get_chain_or_404(db, chain_id))


@router.post("", status_code=status.HTTP_201_CREATED)
def create_chain(
    payload: ChainCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_editor),
) -> dict:
    existing = db.scalar(select(Chain).where(Chain.slug == slugify(payload.name)))
    if existing:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Chain already exists.")
    chain = Chain(name=payload.name, slug=unique_slug(db, payload.name, Chain), website=payload.website)
    db.add(chain)
    db.flush()
    get_or_create_chain_template_menu(db, chain)
    record_audit(
        db,
        user,
        AuditAction.create,
        "chain",
        chain.id,
        f"Created chain {chain.name}",
        None,
        snapshot(chain),
    )
    db.commit()
    return serialize_chain(get_chain_or_404(db, chain.id))


@router.put("/{chain_id}")
def update_chain(
    chain_id: int,
    payload: ChainUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_editor),
) -> dict:
    chain = get_chain_or_404(db, chain_id)
    before = snapshot(chain)
    data = payload.model_dump(exclude_unset=True)
    if "name" in data and data["name"]:
        chain.name = data["name"]
        chain.slug = unique_slug(db, data["name"], Chain, current_id=chain.id)
    if "website" in data:
        chain.website = data["website"]
    db.flush()
    record_audit(
        db,
        user,
        AuditAction.update,
        "chain",
        chain.id,
        f"Updated chain {chain.name}",
        before,
        snapshot(chain),
    )
    db.commit()
    return serialize_chain(get_chain_or_404(db, chain.id))


@router.get("/{chain_id}/template")
def get_chain_template(chain_id: int, db: Session = Depends(get_db)) -> dict:
    chain = get_chain_or_404(db, chain_id)
    menu = get_or_create_chain_template_menu(db, chain)
    return {
        "chain_id": chain.id,
        "menu_id": menu.id,
        "items": [serialize_menu_item(item) for item in menu.items if item.is_available],
    }


@router.post("/{chain_id}/template/items", status_code=status.HTTP_201_CREATED)
def add_template_item(
    chain_id: int,
    payload: MenuItemCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_editor),
) -> dict:
    chain = get_chain_or_404(db, chain_id)
    drink = get_drink_or_404(db, payload.drink_id)
    menu = get_or_create_chain_template_menu(db, chain)
    item, created = add_or_update_menu_item(
        db,
        menu,
        drink=drink,
        amount=payload.amount,
        currency=payload.currency,
        size_label=payload.size_label,
        notes=payload.notes,
        user=user,
        overwrite_existing=True,
        price_is_override=False,
    )
    record_audit(
        db,
        user,
        AuditAction.create if created else AuditAction.update,
        "menu_item",
        item.id,
        f"{'Added' if created else 'Updated'} template {drink.name} for {chain.name}",
        None if created else {"note": "Existing template item updated."},
        snapshot(item),
    )
    db.commit()
    return serialize_menu_item(get_menu_item_or_404(db, item.id))


@router.put("/{chain_id}/template/items/{menu_item_id}")
def update_template_item(
    chain_id: int,
    menu_item_id: int,
    payload: MenuItemUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_editor),
) -> dict:
    chain = get_chain_or_404(db, chain_id)
    item = get_menu_item_or_404(db, menu_item_id)
    if item.menu.chain_id != chain.id or item.menu.scope != MenuScope.chain_template:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Item is not on this chain template.")
    before = {"item": snapshot(item), "price": snapshot(current_price(item))}
    data = payload.model_dump(exclude_unset=True)
    if "notes" in data:
        item.notes = data["notes"]
    if "is_available" in data:
        item.is_available = data["is_available"]
    if "amount" in data and data["amount"] is not None:
        existing_price = current_price(item)
        from app.services.menus import set_current_price

        set_current_price(
            db,
            item,
            amount=data["amount"],
            currency=data.get("currency") or (existing_price.currency if existing_price else "SGD"),
            size_label=data["size_label"] if "size_label" in data else (existing_price.size_label if existing_price else None),
            user=user,
            is_override=False,
        )
    db.flush()
    record_audit(
        db,
        user,
        AuditAction.update,
        "menu_item",
        item.id,
        f"Updated template {item.drink.name} for {chain.name}",
        before,
        {"item": snapshot(item), "price": snapshot(current_price(item))},
    )
    db.commit()
    return serialize_menu_item(get_menu_item_or_404(db, item.id))


@router.delete("/{chain_id}/template/items/{menu_item_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_template_item(
    chain_id: int,
    menu_item_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_editor),
) -> None:
    chain = get_chain_or_404(db, chain_id)
    item = get_menu_item_or_404(db, menu_item_id)
    if item.menu.chain_id != chain.id or item.menu.scope != MenuScope.chain_template:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Item is not on this chain template.")
    before = snapshot(item)
    item.is_available = False
    db.flush()
    record_audit(
        db,
        user,
        AuditAction.delete,
        "menu_item",
        item.id,
        f"Archived template {item.drink.name} for {chain.name}",
        before,
        snapshot(item),
    )
    db.commit()


@router.post("/{chain_id}/sync-template")
def sync_template(
    chain_id: int,
    payload: SyncTemplateRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_editor),
) -> dict:
    chain = get_chain_or_404(db, chain_id)
    synced = sync_template_to_outlets(
        db,
        chain=chain,
        user=user,
        target_shop_ids=payload.target_shop_ids,
        overwrite_outlet_prices=payload.overwrite_outlet_prices,
    )
    db.commit()
    return {
        "chain_id": chain.id,
        "synced_count": len(synced),
        "items": [serialize_menu_item(item) for item in synced],
    }


@router.post("/{chain_id}/duplicate-menu")
def duplicate_menu_within_chain(
    chain_id: int,
    payload: DuplicateMenuRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_editor),
) -> dict:
    chain = get_chain_or_404(db, chain_id)
    source = get_shop_or_404(db, payload.source_shop_id)
    if source.chain_id != chain.id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Source outlet is not in this chain.")

    source_menu = get_or_create_outlet_menu(db, source)
    copied_total = 0
    targets: list[dict] = []
    for target_id in payload.target_shop_ids:
        target = get_shop_or_404(db, target_id)
        if target.chain_id != chain.id:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Target outlet {target_id} is not in this chain.")
        if target.id == source.id:
            continue
        target_menu = get_or_create_outlet_menu(db, target)
        copied = copy_menu_items(
            db,
            source_menu=source_menu,
            target_menu=target_menu,
            user=user,
            drink_ids=payload.drink_ids,
            include_full_menu=payload.include_full_menu,
            overwrite_existing=payload.overwrite_existing,
        )
        copied_total += len(copied)
        targets.append({"shop_id": target.id, "shop_name": target.name, "copied_count": len(copied)})

    db.commit()
    return {
        "chain_id": chain.id,
        "source_shop_id": source.id,
        "copied_count": copied_total,
        "targets": targets,
    }
