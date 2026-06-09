from __future__ import annotations

from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.models import UserRole


class UserPublic(BaseModel):
    id: int
    name: str
    email: str
    role: UserRole

    model_config = ConfigDict(from_attributes=True)


class UserCreate(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    email: str = Field(min_length=5, max_length=255)
    api_key: str = Field(min_length=8, max_length=120)
    role: UserRole = UserRole.editor


class ChainCreate(BaseModel):
    name: str = Field(min_length=2, max_length=160)
    website: str | None = None


class ChainUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=160)
    website: str | None = None


class ShopCreate(BaseModel):
    name: str = Field(min_length=2, max_length=180)
    location: str = Field(min_length=2, max_length=180)
    address: str | None = None
    neighborhood: str | None = None
    chain_id: int | None = None
    chain_name: str | None = None


class ShopUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=180)
    location: str | None = Field(default=None, min_length=2, max_length=180)
    address: str | None = None
    neighborhood: str | None = None
    chain_id: int | None = None
    chain_name: str | None = None


class DrinkCreate(BaseModel):
    name: str = Field(min_length=2, max_length=140)
    drink_type: str = Field(min_length=2, max_length=80)
    default_size: str | None = None
    description: str | None = None


class DrinkUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=140)
    drink_type: str | None = Field(default=None, min_length=2, max_length=80)
    default_size: str | None = None
    description: str | None = None
    is_active: bool | None = None


class MenuItemCreate(BaseModel):
    drink_id: int
    amount: Decimal = Field(gt=0, max_digits=8, decimal_places=2)
    currency: str = Field(default="SGD", min_length=3, max_length=3)
    size_label: str | None = None
    notes: str | None = None


class MenuItemUpdate(BaseModel):
    amount: Decimal | None = Field(default=None, gt=0, max_digits=8, decimal_places=2)
    currency: str | None = Field(default=None, min_length=3, max_length=3)
    size_label: str | None = None
    notes: str | None = None
    is_available: bool | None = None


class CopyMenuRequest(BaseModel):
    target_shop_id: int
    drink_ids: list[int] | None = None
    include_full_menu: bool = True
    overwrite_existing: bool = False


class DuplicateMenuRequest(BaseModel):
    source_shop_id: int
    target_shop_ids: list[int]
    drink_ids: list[int] | None = None
    include_full_menu: bool = True
    overwrite_existing: bool = False


class SyncTemplateRequest(BaseModel):
    target_shop_ids: list[int] | None = None
    overwrite_outlet_prices: bool = False


class CompareSort(str):
    price = "price"
    shop_name = "shop_name"
    drink_type = "drink_type"
    chain = "chain"


SortBy = Literal["price", "shop_name", "drink_type", "chain"]
