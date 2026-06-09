from __future__ import annotations

from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload, selectinload

from app.audit import record_audit, snapshot
from app.auth import get_current_editor
from app.database import get_db
from app.models import AuditAction, Chain, Drink, Menu, MenuItem, MenuScope, Price, Shop, User
from app.schemas import CopyMenuRequest, MenuItemCreate, ShopCreate, ShopUpdate, SortBy
from app.services.menus import (
    add_or_update_menu_item,
    copy_menu_items,
    current_price,
    detect_chain_for_shop,
    find_chain_by_name,
    get_drink_or_404,
    get_or_create_outlet_menu,
    get_shop_or_404,
    serialize_menu_item,
    serialize_shop,
    size_category,
)

router = APIRouter(prefix="/api", tags=["shops"])


def _normalize_duplicate_key(value: str | None) -> str:
    return " ".join((value or "").casefold().split())


def _find_duplicate_shop(
    db: Session,
    *,
    name: str,
    location: str,
    address: str | None,
    chain_id: int | None,
    exclude_shop_id: int | None = None,
) -> Shop | None:
    shops = db.scalars(select(Shop).where(Shop.is_active.is_(True))).all()
    wanted_name = _normalize_duplicate_key(name)
    wanted_location = _normalize_duplicate_key(location)
    wanted_address = _normalize_duplicate_key(address)

    for shop in shops:
        if exclude_shop_id is not None and shop.id == exclude_shop_id:
            continue

        same_name_location = (
            _normalize_duplicate_key(shop.name) == wanted_name
            and _normalize_duplicate_key(shop.location) == wanted_location
        )
        same_address = bool(wanted_address) and _normalize_duplicate_key(shop.address) == wanted_address
        same_chain_location = (
            chain_id is not None
            and shop.chain_id == chain_id
            and _normalize_duplicate_key(shop.location) == wanted_location
        )

        if same_name_location or same_address or same_chain_location:
            return shop
    return None


def _shops_query():
    return (
        select(Shop)
        .options(
            joinedload(Shop.chain),
            selectinload(Shop.menus).selectinload(Menu.items).selectinload(MenuItem.drink),
            selectinload(Shop.menus).selectinload(Menu.items).selectinload(MenuItem.prices),
        )
        .where(Shop.is_active.is_(True))
    )


def _active_items(shop: Shop) -> list[MenuItem]:
    items: list[MenuItem] = []
    for menu in shop.menus:
        if menu.scope == MenuScope.outlet and menu.is_active:
            items.extend([item for item in menu.items if item.is_available])
    return items


def _row_text(shop: Shop, item: MenuItem | None = None) -> str:
    parts = [
        shop.name,
        shop.location,
        shop.address or "",
        shop.neighborhood or "",
        shop.chain.name if shop.chain else "",
    ]
    if item:
        parts.extend([item.drink.name, item.drink.drink_type, item.notes or ""])
    return " ".join(parts).lower()


def _passes_price(item: MenuItem, min_price: Decimal | None, max_price: Decimal | None) -> bool:
    price = current_price(item)
    if not price:
        return False
    if min_price is not None and price.amount < min_price:
        return False
    if max_price is not None and price.amount > max_price:
        return False
    return True


def _dashboard_items(
    shop: Shop,
    term: str | None,
    min_price: Decimal | None,
    max_price: Decimal | None,
) -> list[tuple[MenuItem, Price]]:
    matched_items: list[tuple[MenuItem, Price]] = []
    shop_matches = term is not None and term in _row_text(shop)

    for item in _active_items(shop):
        price = current_price(item)
        if not price:
            continue
        if term and not shop_matches and term not in _row_text(shop, item):
            continue
        if not _passes_price(item, min_price, max_price):
            continue
        matched_items.append((item, price))

    return matched_items


def _shop_average_summary(
    shop: Shop,
    term: str | None = None,
    min_price: Decimal | None = None,
    max_price: Decimal | None = None,
) -> dict | None:
    items = _dashboard_items(shop, term, min_price, max_price)
    if not items:
        return None

    amounts = [price.amount for _, price in items]
    average = sum(amounts, Decimal("0")) / Decimal(len(amounts))
    cheapest_item, cheapest_price = min(items, key=lambda row: row[1].amount)
    priciest_item, priciest_price = max(items, key=lambda row: row[1].amount)

    return {
        "shop_id": shop.id,
        "shop_name": shop.name,
        "location": shop.location,
        "chain": shop.chain.name if shop.chain else None,
        "average_price": float(average.quantize(Decimal("0.01"))),
        "price_count": len(items),
        "min_price": float(cheapest_price.amount),
        "min_drink": cheapest_item.drink.name,
        "max_price": float(priciest_price.amount),
        "max_drink": priciest_item.drink.name,
        "currency": cheapest_price.currency,
    }


@router.get("/dashboard/shop-averages")
def shop_average_dashboard(
    search: str | None = None,
    min_price: Decimal | None = Query(default=None, ge=0),
    max_price: Decimal | None = Query(default=None, ge=0),
    chain_id: int | None = None,
    db: Session = Depends(get_db),
) -> list[dict]:
    shops = db.scalars(_shops_query()).all()
    term = search.lower().strip() if search else None
    summaries: list[dict] = []

    for shop in shops:
        if chain_id and shop.chain_id != chain_id:
            continue
        summary = _shop_average_summary(shop, term, min_price, max_price)
        if summary:
            summaries.append(summary)

    return sorted(summaries, key=lambda row: (row["average_price"], row["shop_name"].lower()))


@router.get("/shops")
def list_shops(
    search: str | None = None,
    min_price: Decimal | None = Query(default=None, ge=0),
    max_price: Decimal | None = Query(default=None, ge=0),
    chain_id: int | None = None,
    sort_by: SortBy = "shop_name",
    db: Session = Depends(get_db),
) -> list[dict]:
    shops = db.scalars(_shops_query()).all()
    term = search.lower().strip() if search else None

    filtered: list[Shop] = []
    for shop in shops:
        if chain_id and shop.chain_id != chain_id:
            continue
        items = _active_items(shop)
        if term and term not in _row_text(shop) and not any(term in _row_text(shop, item) for item in items):
            continue
        if min_price is not None or max_price is not None:
            if not any(_passes_price(item, min_price, max_price) for item in items):
                continue
        filtered.append(shop)

    def sort_key(shop: Shop):
        items = _active_items(shop)
        prices = [current_price(item).amount for item in items if current_price(item)]
        if sort_by == "price":
            return (min(prices) if prices else Decimal("999999"), shop.name.lower())
        if sort_by == "chain":
            return ((shop.chain.name if shop.chain else "").lower(), shop.name.lower())
        if sort_by == "drink_type":
            first_type = min([item.drink.drink_type.lower() for item in items], default="")
            return (first_type, shop.name.lower())
        return shop.name.lower()

    return [serialize_shop(shop) for shop in sorted(filtered, key=sort_key)]


@router.get("/shops/{shop_id}")
def get_shop(shop_id: int, db: Session = Depends(get_db)) -> dict:
    return serialize_shop(get_shop_or_404(db, shop_id), include_inactive_items=True)


@router.post("/shops", status_code=status.HTTP_201_CREATED)
def create_shop(
    payload: ShopCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_editor),
) -> dict:
    existing_chain = find_chain_by_name(db, payload.chain_name) if payload.chain_name else None
    chain = detect_chain_for_shop(db, payload.name, payload.chain_id, payload.chain_name)
    duplicate = _find_duplicate_shop(
        db,
        name=payload.name,
        location=payload.location,
        address=payload.address,
        chain_id=chain.id if chain else None,
    )
    if duplicate:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"That shop looks like a duplicate of {duplicate.name} at {duplicate.location}.",
        )
    if chain and payload.chain_name and existing_chain is None:
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

    shop = Shop(
        name=payload.name,
        location=payload.location,
        address=payload.address,
        neighborhood=payload.neighborhood,
        chain_id=chain.id if chain else None,
    )
    db.add(shop)
    db.flush()
    get_or_create_outlet_menu(db, shop)
    record_audit(
        db,
        user,
        AuditAction.create,
        "shop",
        shop.id,
        f"Created shop {shop.name}",
        None,
        snapshot(shop),
    )
    db.commit()
    return serialize_shop(get_shop_or_404(db, shop.id))


@router.put("/shops/{shop_id}")
def update_shop(
    shop_id: int,
    payload: ShopUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_editor),
) -> dict:
    shop = get_shop_or_404(db, shop_id)
    before = snapshot(shop)
    data = payload.model_dump(exclude_unset=True)
    chain_id = data.pop("chain_id", None)
    chain_name = data.pop("chain_name", None)
    for key, value in data.items():
        setattr(shop, key, value)
    if chain_id is not None or chain_name is not None:
        existing_chain = find_chain_by_name(db, chain_name) if chain_name else None
        chain = detect_chain_for_shop(db, shop.name, chain_id, chain_name)
        shop.chain_id = chain.id if chain else None
        if chain and chain_name and existing_chain is None:
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
    duplicate = _find_duplicate_shop(
        db,
        name=shop.name,
        location=shop.location,
        address=shop.address,
        chain_id=shop.chain_id,
        exclude_shop_id=shop.id,
    )
    if duplicate:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"That update would duplicate {duplicate.name} at {duplicate.location}.",
        )
    db.flush()
    record_audit(
        db,
        user,
        AuditAction.update,
        "shop",
        shop.id,
        f"Updated shop {shop.name}",
        before,
        snapshot(shop),
    )
    db.commit()
    return serialize_shop(get_shop_or_404(db, shop.id))


@router.delete("/shops/{shop_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_shop(
    shop_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_editor),
) -> None:
    shop = get_shop_or_404(db, shop_id)
    before = snapshot(shop)
    shop.is_active = False
    db.flush()
    record_audit(
        db,
        user,
        AuditAction.delete,
        "shop",
        shop.id,
        f"Archived shop {shop.name}",
        before,
        snapshot(shop),
    )
    db.commit()


@router.post("/shops/{shop_id}/menu/items", status_code=status.HTTP_201_CREATED)
def add_shop_menu_item(
    shop_id: int,
    payload: MenuItemCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_editor),
) -> dict:
    shop = get_shop_or_404(db, shop_id)
    drink = get_drink_or_404(db, payload.drink_id)
    menu = get_or_create_outlet_menu(db, shop)
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
        price_is_override=True,
    )
    record_audit(
        db,
        user,
        AuditAction.create if created else AuditAction.update,
        "menu_item",
        item.id,
        f"{'Added' if created else 'Updated'} {drink.name} at {shop.name}",
        None if created else {"note": "Existing menu item updated through add endpoint."},
        snapshot(item),
    )
    db.commit()
    return {**serialize_menu_item(item), "created": created}


@router.post("/shops/{source_shop_id}/copy-menu")
def copy_shop_menu(
    source_shop_id: int,
    payload: CopyMenuRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_editor),
) -> dict:
    source = get_shop_or_404(db, source_shop_id)
    target = get_shop_or_404(db, payload.target_shop_id)
    source_menu = get_or_create_outlet_menu(db, source)
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
    db.commit()
    return {
        "source_shop_id": source.id,
        "target_shop_id": target.id,
        "copied_count": len(copied),
        "items": [serialize_menu_item(item) for item in copied],
    }


@router.get("/compare")
def compare_prices(
    search: str | None = None,
    min_price: Decimal | None = Query(default=None, ge=0),
    max_price: Decimal | None = Query(default=None, ge=0),
    chain_id: int | None = None,
    sort_by: SortBy = "price",
    db: Session = Depends(get_db),
) -> list[dict]:
    shops = db.scalars(_shops_query()).all()
    term = search.lower().strip() if search else None
    rows: list[dict] = []

    for shop in shops:
        if chain_id and shop.chain_id != chain_id:
            continue
        for item in _active_items(shop):
            price = current_price(item)
            if not price:
                continue
            if term and term not in _row_text(shop, item):
                continue
            if not _passes_price(item, min_price, max_price):
                continue
            rows.append(
                {
                    "shop_id": shop.id,
                    "shop_name": shop.name,
                    "location": shop.location,
                    "chain": shop.chain.name if shop.chain else None,
                    "drink_id": item.drink_id,
                    "drink_name": item.drink.name,
                    "drink_type": item.drink.drink_type,
                    "price": float(price.amount),
                    "currency": price.currency,
                    "size_label": price.size_label,
                    "size_category": size_category(price.size_label),
                    "is_override": price.is_override,
                }
            )

    def sort_key(row: dict):
        if sort_by == "shop_name":
            return (row["shop_name"].lower(), row["drink_name"].lower())
        if sort_by == "drink_type":
            return (row["drink_type"].lower(), row["price"])
        if sort_by == "chain":
            return ((row["chain"] or "").lower(), row["shop_name"].lower())
        return (row["price"], row["shop_name"].lower())

    return sorted(rows, key=sort_key)
