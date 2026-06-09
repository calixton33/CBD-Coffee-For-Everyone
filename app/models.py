from __future__ import annotations

import enum
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    JSON,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class UserRole(str, enum.Enum):
    admin = "admin"
    editor = "editor"
    viewer = "viewer"


class MenuScope(str, enum.Enum):
    chain_template = "chain_template"
    outlet = "outlet"


class AuditAction(str, enum.Enum):
    create = "create"
    update = "update"
    delete = "delete"
    copy = "copy"
    sync = "sync"


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    api_key_hash: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    role: Mapped[UserRole] = mapped_column(Enum(UserRole), default=UserRole.editor)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    edits: Mapped[list[EditHistory]] = relationship(back_populates="user")


class Chain(Base):
    __tablename__ = "chains"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    slug: Mapped[str] = mapped_column(String(180), unique=True, nullable=False)
    website: Mapped[str | None] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    shops: Mapped[list[Shop]] = relationship(back_populates="chain")
    menus: Mapped[list[Menu]] = relationship(back_populates="chain")


class Shop(Base):
    __tablename__ = "shops"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(180), nullable=False)
    location: Mapped[str] = mapped_column(String(180), nullable=False)
    address: Mapped[str | None] = mapped_column(String(255))
    neighborhood: Mapped[str | None] = mapped_column(String(120))
    chain_id: Mapped[int | None] = mapped_column(ForeignKey("chains.id"))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )

    chain: Mapped[Chain | None] = relationship(back_populates="shops")
    menus: Mapped[list[Menu]] = relationship(back_populates="shop")


class Drink(Base):
    __tablename__ = "drinks"
    __table_args__ = (UniqueConstraint("name", "drink_type", name="uq_drink_name_type"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(140), nullable=False)
    drink_type: Mapped[str] = mapped_column(String(80), nullable=False)
    default_size: Mapped[str | None] = mapped_column(String(60))
    description: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    menu_items: Mapped[list[MenuItem]] = relationship(back_populates="drink")


class Menu(Base):
    __tablename__ = "menus"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(180), nullable=False)
    scope: Mapped[MenuScope] = mapped_column(Enum(MenuScope), nullable=False)
    chain_id: Mapped[int | None] = mapped_column(ForeignKey("chains.id"))
    shop_id: Mapped[int | None] = mapped_column(ForeignKey("shops.id"))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )

    chain: Mapped[Chain | None] = relationship(back_populates="menus")
    shop: Mapped[Shop | None] = relationship(back_populates="menus")
    items: Mapped[list[MenuItem]] = relationship(back_populates="menu")


class MenuItem(Base):
    __tablename__ = "menu_items"
    __table_args__ = (UniqueConstraint("menu_id", "drink_id", name="uq_menu_drink"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    menu_id: Mapped[int] = mapped_column(ForeignKey("menus.id"), nullable=False)
    drink_id: Mapped[int] = mapped_column(ForeignKey("drinks.id"), nullable=False)
    source_template_item_id: Mapped[int | None] = mapped_column(ForeignKey("menu_items.id"))
    copied_from_menu_item_id: Mapped[int | None] = mapped_column(ForeignKey("menu_items.id"))
    notes: Mapped[str | None] = mapped_column(Text)
    is_available: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )

    menu: Mapped[Menu] = relationship(back_populates="items", foreign_keys=[menu_id])
    drink: Mapped[Drink] = relationship(back_populates="menu_items")
    prices: Mapped[list[Price]] = relationship(
        back_populates="menu_item",
        order_by="desc(Price.effective_from)",
        cascade="all, delete-orphan",
    )
    source_template_item: Mapped[MenuItem | None] = relationship(
        remote_side=[id], foreign_keys=[source_template_item_id]
    )
    copied_from_menu_item: Mapped[MenuItem | None] = relationship(
        remote_side=[id], foreign_keys=[copied_from_menu_item_id]
    )


class Price(Base):
    __tablename__ = "prices"

    id: Mapped[int] = mapped_column(primary_key=True)
    menu_item_id: Mapped[int] = mapped_column(ForeignKey("menu_items.id"), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(8, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), default="SGD")
    size_label: Mapped[str | None] = mapped_column(String(60))
    is_override: Mapped[bool] = mapped_column(Boolean, default=False)
    effective_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    effective_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    changed_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))

    menu_item: Mapped[MenuItem] = relationship(back_populates="prices")
    changed_by: Mapped[User | None] = relationship()


class EditHistory(Base):
    __tablename__ = "edit_history"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    editor_name: Mapped[str] = mapped_column(String(120), nullable=False)
    action: Mapped[AuditAction] = mapped_column(Enum(AuditAction), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(80), nullable=False)
    entity_id: Mapped[int | None] = mapped_column(nullable=True)
    summary: Mapped[str] = mapped_column(String(255), nullable=False)
    before: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    after: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    user: Mapped[User | None] = relationship(back_populates="edits")
