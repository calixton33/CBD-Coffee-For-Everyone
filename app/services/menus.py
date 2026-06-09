from __future__ import annotations

import re
from decimal import Decimal

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload, selectinload

from app.audit import record_audit, snapshot
from app.models import (
    AuditAction,
    Chain,
    Drink,
    Menu,
    MenuItem,
    MenuScope,
    Price,
    Shop,
    User,
    utc_now,
)


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or "item"


def current_price(item: MenuItem) -> Price | None:
    for price in item.prices:
        if price.effective_to is None:
            return price
    return None


def size_category(size_label: str | None) -> str:
    if not size_label:
        return "Not sure"

    value = size_label.strip().lower()
    match = re.search(r"(\d+(?:\.\d+)?)\s*ml\b", value)
    if not match:
        return "Not sure"

    size_ml = Decimal(match.group(1))
    if size_ml in {Decimal("400"), Decimal("450"), Decimal("500")}:
        return f"{int(size_ml)}ml"
    return "Not sure"


def get_shop_or_404(db: Session, shop_id: int) -> Shop:
    shop = db.scalar(
        select(Shop)
        .options(
            joinedload(Shop.chain),
            selectinload(Shop.menus).selectinload(Menu.items).selectinload(MenuItem.drink),
            selectinload(Shop.menus)
            .selectinload(Menu.items)
            .selectinload(MenuItem.prices),
        )
        .where(Shop.id == shop_id, Shop.is_active.is_(True))
    )
    if not shop:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Shop not found.")
    return shop


def get_chain_or_404(db: Session, chain_id: int) -> Chain:
    chain = db.scalar(
        select(Chain)
        .options(
            selectinload(Chain.shops),
            selectinload(Chain.menus).selectinload(Menu.items).selectinload(MenuItem.drink),
            selectinload(Chain.menus)
            .selectinload(Menu.items)
            .selectinload(MenuItem.prices),
        )
        .where(Chain.id == chain_id)
    )
    if not chain:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Chain not found.")
    return chain


def get_drink_or_404(db: Session, drink_id: int) -> Drink:
    drink = db.scalar(select(Drink).where(Drink.id == drink_id, Drink.is_active.is_(True)))
    if not drink:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Drink not found.")
    return drink


def get_menu_item_or_404(db: Session, menu_item_id: int) -> MenuItem:
    item = db.scalar(
        select(MenuItem)
        .options(
            joinedload(MenuItem.menu).joinedload(Menu.shop),
            joinedload(MenuItem.menu).joinedload(Menu.chain),
            joinedload(MenuItem.drink),
            selectinload(MenuItem.prices),
        )
        .where(MenuItem.id == menu_item_id)
    )
    if not item:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Menu item not found.")
    return item


def unique_slug(db: Session, name: str, model: type[Chain], current_id: int | None = None) -> str:
    base = slugify(name)
    candidate = base
    suffix = 2
    while True:
        query = select(model).where(model.slug == candidate)
        if current_id is not None:
            query = query.where(model.id != current_id)
        exists = db.scalar(query)
        if not exists:
            return candidate
        candidate = f"{base}-{suffix}"
        suffix += 1


def find_chain_by_name(db: Session, chain_name: str | None) -> Chain | None:
    if not chain_name:
        return None
    normalized = slugify(chain_name)
    return db.scalar(select(Chain).where(Chain.slug == normalized))


def create_chain_if_needed(db: Session, name: str) -> Chain:
    existing = find_chain_by_name(db, name)
    if existing:
        return existing
    chain = Chain(name=name.strip(), slug=unique_slug(db, name, Chain))
    db.add(chain)
    db.flush()
    return chain


def detect_chain_for_shop(
    db: Session,
    shop_name: str,
    explicit_chain_id: int | None = None,
    explicit_chain_name: str | None = None,
) -> Chain | None:
    if explicit_chain_id:
        chain = db.get(Chain, explicit_chain_id)
        if not chain:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Chain not found.")
        return chain
    if explicit_chain_name:
        return create_chain_if_needed(db, explicit_chain_name)

    normalized_shop = slugify(shop_name)
    chains = db.scalars(select(Chain)).all()
    for chain in chains:
        chain_slug = slugify(chain.name)
        if normalized_shop == chain_slug or normalized_shop.startswith(f"{chain_slug}-"):
            return chain
    return None


def get_or_create_outlet_menu(db: Session, shop: Shop) -> Menu:
    menu = db.scalar(
        select(Menu).where(
            Menu.shop_id == shop.id,
            Menu.scope == MenuScope.outlet,
            Menu.is_active.is_(True),
        )
    )
    if menu:
        return menu
    menu = Menu(name=f"{shop.name} menu", scope=MenuScope.outlet, shop_id=shop.id)
    db.add(menu)
    db.flush()
    return menu


def get_or_create_chain_template_menu(db: Session, chain: Chain) -> Menu:
    menu = db.scalar(
        select(Menu).where(
            Menu.chain_id == chain.id,
            Menu.scope == MenuScope.chain_template,
            Menu.is_active.is_(True),
        )
    )
    if menu:
        return menu
    menu = Menu(
        name=f"{chain.name} template menu",
        scope=MenuScope.chain_template,
        chain_id=chain.id,
    )
    db.add(menu)
    db.flush()
    return menu


def set_current_price(
    db: Session,
    item: MenuItem,
    *,
    amount: Decimal,
    currency: str = "SGD",
    size_label: str | None = None,
    user: User | None = None,
    is_override: bool = False,
) -> Price:
    now = utc_now()
    for price in item.prices:
        if price.effective_to is None:
            price.effective_to = now
    new_price = Price(
        menu_item_id=item.id,
        amount=amount,
        currency=currency.upper(),
        size_label=size_label,
        is_override=is_override,
        effective_from=now,
        changed_by_user_id=user.id if user else None,
    )
    db.add(new_price)
    db.flush()
    db.refresh(item)
    return new_price


def add_or_update_menu_item(
    db: Session,
    menu: Menu,
    *,
    drink: Drink,
    amount: Decimal,
    currency: str = "SGD",
    size_label: str | None = None,
    notes: str | None = None,
    user: User | None = None,
    source_template_item_id: int | None = None,
    copied_from_menu_item_id: int | None = None,
    overwrite_existing: bool = True,
    price_is_override: bool = False,
) -> tuple[MenuItem, bool]:
    existing = db.scalar(
        select(MenuItem).where(MenuItem.menu_id == menu.id, MenuItem.drink_id == drink.id)
    )
    created = existing is None
    if existing and not overwrite_existing:
        return existing, False

    item = existing or MenuItem(menu_id=menu.id, drink_id=drink.id)
    if created:
        db.add(item)

    item.notes = notes
    item.is_available = True
    if source_template_item_id is not None:
        item.source_template_item_id = source_template_item_id
    if copied_from_menu_item_id is not None:
        item.copied_from_menu_item_id = copied_from_menu_item_id

    db.flush()

    existing_price = current_price(item)
    price_changed = (
        existing_price is None
        or existing_price.amount != amount
        or existing_price.currency != currency.upper()
        or existing_price.size_label != size_label
        or existing_price.is_override != price_is_override
    )
    if price_changed:
        set_current_price(
            db,
            item,
            amount=amount,
            currency=currency,
            size_label=size_label,
            user=user,
            is_override=price_is_override,
        )
    return item, created


def serialize_price(price: Price | None) -> dict | None:
    if not price:
        return None
    return {
        "id": price.id,
        "amount": float(price.amount),
        "currency": price.currency,
        "size_label": price.size_label,
        "size_category": size_category(price.size_label),
        "is_override": price.is_override,
        "effective_from": price.effective_from.isoformat(),
    }


def serialize_menu_item(item: MenuItem) -> dict:
    price = current_price(item)
    return {
        "id": item.id,
        "drink_id": item.drink_id,
        "drink_name": item.drink.name,
        "drink_type": item.drink.drink_type,
        "default_size": item.drink.default_size,
        "notes": item.notes,
        "is_available": item.is_available,
        "source_template_item_id": item.source_template_item_id,
        "copied_from_menu_item_id": item.copied_from_menu_item_id,
        "price": serialize_price(price),
    }


def serialize_shop(shop: Shop, include_inactive_items: bool = False) -> dict:
    outlet_menu = next(
        (
            menu
            for menu in shop.menus
            if menu.scope == MenuScope.outlet and menu.is_active
        ),
        None,
    )
    items = []
    if outlet_menu:
        items = [
            serialize_menu_item(item)
            for item in outlet_menu.items
            if include_inactive_items or item.is_available
        ]
        items.sort(key=lambda row: (row["drink_type"].lower(), row["drink_name"].lower()))
    return {
        "id": shop.id,
        "name": shop.name,
        "location": shop.location,
        "address": shop.address,
        "neighborhood": shop.neighborhood,
        "chain": (
            {"id": shop.chain.id, "name": shop.chain.name, "slug": shop.chain.slug}
            if shop.chain
            else None
        ),
        "items": items,
    }


def serialize_chain(chain: Chain) -> dict:
    template = next(
        (
            menu
            for menu in chain.menus
            if menu.scope == MenuScope.chain_template and menu.is_active
        ),
        None,
    )
    return {
        "id": chain.id,
        "name": chain.name,
        "slug": chain.slug,
        "website": chain.website,
        "outlets": [
            {
                "id": shop.id,
                "name": shop.name,
                "location": shop.location,
                "address": shop.address,
            }
            for shop in sorted(chain.shops, key=lambda item: item.name.lower())
            if shop.is_active
        ],
        "template_items": (
            [
                serialize_menu_item(item)
                for item in template.items
                if item.is_available
            ]
            if template
            else []
        ),
    }


def copy_menu_items(
    db: Session,
    *,
    source_menu: Menu,
    target_menu: Menu,
    user: User,
    drink_ids: list[int] | None = None,
    include_full_menu: bool = True,
    overwrite_existing: bool = False,
    source_template_item_id: int | None = None,
) -> list[MenuItem]:
    allowed_drinks = set(drink_ids or [])
    copied: list[MenuItem] = []

    for source_item in source_menu.items:
        if not source_item.is_available:
            continue
        if not include_full_menu and (
            not allowed_drinks or source_item.drink_id not in allowed_drinks
        ):
            continue
        price = current_price(source_item)
        if not price:
            continue

        before_item = db.scalar(
            select(MenuItem).where(
                MenuItem.menu_id == target_menu.id,
                MenuItem.drink_id == source_item.drink_id,
            )
        )
        if before_item and not overwrite_existing:
            continue
        before = snapshot(before_item)
        target_item, _ = add_or_update_menu_item(
            db,
            target_menu,
            drink=source_item.drink,
            amount=price.amount,
            currency=price.currency,
            size_label=price.size_label,
            notes=source_item.notes,
            user=user,
            source_template_item_id=source_template_item_id
            if source_template_item_id is not None
            else source_item.source_template_item_id,
            copied_from_menu_item_id=source_item.id,
            overwrite_existing=overwrite_existing,
            price_is_override=False,
        )
        after = snapshot(target_item)
        if before != after:
            record_audit(
                db,
                user,
                AuditAction.copy,
                "menu_item",
                target_item.id,
                f"Copied {source_item.drink.name} to {target_menu.name}",
                before,
                after,
            )
        copied.append(target_item)
    return copied


def sync_template_to_outlets(
    db: Session,
    *,
    chain: Chain,
    user: User | None,
    target_shop_ids: list[int] | None = None,
    overwrite_outlet_prices: bool = False,
) -> list[MenuItem]:
    template = get_or_create_chain_template_menu(db, chain)
    target_ids = set(target_shop_ids or [])
    synced: list[MenuItem] = []

    for shop in chain.shops:
        if not shop.is_active:
            continue
        if target_ids and shop.id not in target_ids:
            continue
        outlet_menu = get_or_create_outlet_menu(db, shop)
        for template_item in template.items:
            if not template_item.is_available:
                continue
            template_price = current_price(template_item)
            if not template_price:
                continue

            existing = db.scalar(
                select(MenuItem).where(
                    MenuItem.menu_id == outlet_menu.id,
                    MenuItem.drink_id == template_item.drink_id,
                )
            )
            before = snapshot(existing)
            existing_price = current_price(existing) if existing else None
            preserve_override = (
                existing_price is not None
                and existing_price.is_override
                and not overwrite_outlet_prices
            )
            amount = existing_price.amount if preserve_override else template_price.amount
            currency = existing_price.currency if preserve_override else template_price.currency
            size_label = (
                existing_price.size_label if preserve_override else template_price.size_label
            )

            item, _ = add_or_update_menu_item(
                db,
                outlet_menu,
                drink=template_item.drink,
                amount=amount,
                currency=currency,
                size_label=size_label,
                notes=template_item.notes,
                user=user,
                source_template_item_id=template_item.id,
                overwrite_existing=True,
                price_is_override=preserve_override,
            )
            after = snapshot(item)
            if before != after and user:
                record_audit(
                    db,
                    user,
                    AuditAction.sync,
                    "menu_item",
                    item.id,
                    f"Synced {template_item.drink.name} to {shop.name}",
                    before,
                    after,
                )
            synced.append(item)
    return synced
