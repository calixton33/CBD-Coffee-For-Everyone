from __future__ import annotations

from decimal import Decimal

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.auth import hash_api_key
from app.config import _normalize_database_url
from app.database import Base
from app.models import Chain, Drink, MenuItem, Shop, User, UserRole
from app.routers.shops import _find_duplicate_shop
from app.routers.shops import _shop_average_summary
from app.services.menus import (
    add_or_update_menu_item,
    current_price,
    get_or_create_chain_template_menu,
    get_or_create_outlet_menu,
    sync_template_to_outlets,
    size_category,
)


def make_session():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine, autoflush=False, autocommit=False)()


def test_template_sync_preserves_outlet_override():
    db = make_session()
    user = User(
        name="Editor",
        email="editor@example.com",
        role=UserRole.admin,
        api_key_hash=hash_api_key("secret-key"),
    )
    chain = Chain(name="Chain", slug="chain")
    shop = Shop(name="Chain Outlet", location="CBD", chain=chain)
    drink = Drink(name="Flat White", drink_type="Milk Coffee")
    db.add_all([user, chain, shop, drink])
    db.flush()

    template = get_or_create_chain_template_menu(db, chain)
    add_or_update_menu_item(
        db,
        template,
        drink=drink,
        amount=Decimal("5.00"),
        user=user,
        price_is_override=False,
    )
    sync_template_to_outlets(db, chain=chain, user=user)

    outlet_menu = get_or_create_outlet_menu(db, shop)
    outlet_item = db.scalar(
        select(MenuItem).where(MenuItem.menu_id == outlet_menu.id, MenuItem.drink_id == drink.id)
    )
    assert outlet_item is not None

    add_or_update_menu_item(
        db,
        outlet_menu,
        drink=drink,
        amount=Decimal("5.75"),
        user=user,
        price_is_override=True,
    )

    add_or_update_menu_item(
        db,
        template,
        drink=drink,
        amount=Decimal("5.25"),
        user=user,
        price_is_override=False,
    )
    sync_template_to_outlets(db, chain=chain, user=user, overwrite_outlet_prices=False)

    db.refresh(outlet_item)
    price = current_price(outlet_item)
    assert price is not None
    assert price.amount == Decimal("5.75")
    assert price.is_override is True


def test_duplicate_shop_detection_matches_chain_location():
    db = make_session()
    chain = Chain(name="Ya Kun Kaya Toast", slug="ya-kun-kaya-toast")
    existing = Shop(
        name="Ya Kun Kaya Toast",
        location="Raffles City",
        address="252 North Bridge Road #B1-80, Singapore 179103",
        chain=chain,
    )
    db.add_all([chain, existing])
    db.flush()

    duplicate = _find_duplicate_shop(
        db,
        name="Ya Kun Kaya Toast Raffles City",
        location="Raffles City",
        address="252 North Bridge Road #B1-80, Singapore 179103",
        chain_id=chain.id,
    )

    assert duplicate == existing


def test_shop_average_summary_uses_current_active_prices():
    db = make_session()
    user = User(
        name="Editor",
        email="editor@example.com",
        role=UserRole.admin,
        api_key_hash=hash_api_key("secret-key"),
    )
    shop = Shop(name="Coffee Bar", location="Raffles Place")
    latte = Drink(name="Latte", drink_type="Milk Coffee")
    americano = Drink(name="Americano", drink_type="Black Coffee")
    db.add_all([user, shop, latte, americano])
    db.flush()

    menu = get_or_create_outlet_menu(db, shop)
    add_or_update_menu_item(db, menu, drink=latte, amount=Decimal("6.00"), user=user)
    add_or_update_menu_item(db, menu, drink=americano, amount=Decimal("4.00"), user=user)

    summary = _shop_average_summary(shop)

    assert summary is not None
    assert summary["average_price"] == 5.00
    assert summary["price_count"] == 2
    assert summary["min_drink"] == "Americano"
    assert summary["max_drink"] == "Latte"


def test_size_category_uses_supported_ml_sizes():
    assert size_category("400ml") == "400ml"
    assert size_category("450 ml") == "450ml"
    assert size_category("500ml") == "500ml"
    assert size_category("350ml") == "Not sure"
    assert size_category("600ml") == "Not sure"
    assert size_category("Regular") == "Not sure"
    assert size_category(None) == "Not sure"


def test_database_url_normalizes_common_postgres_urls_to_installed_driver():
    assert (
        _normalize_database_url("postgres://user:pass@example.com/db")
        == "postgresql+psycopg://user:pass@example.com/db"
    )
    assert (
        _normalize_database_url("postgresql://user:pass@example.com/db")
        == "postgresql+psycopg://user:pass@example.com/db"
    )
    assert (
        _normalize_database_url("postgresql+psycopg://user:pass@example.com/db")
        == "postgresql+psycopg://user:pass@example.com/db"
    )


def test_production_startup_does_not_run_seed(monkeypatch):
    from app import main

    seed_called = False

    def fake_seed_database(db):
        nonlocal seed_called
        seed_called = True

    class FakeSession:
        def __enter__(self):
            return object()

        def __exit__(self, exc_type, exc, traceback):
            return None

    class FakeSettings:
        auto_seed = True
        is_production = True

    monkeypatch.setattr(main, "settings", FakeSettings())
    monkeypatch.setattr(main, "create_db", lambda: None)
    monkeypatch.setattr(main, "SessionLocal", lambda: FakeSession())
    monkeypatch.setattr(main, "seed_database", fake_seed_database)

    main.on_startup()

    assert seed_called is False
