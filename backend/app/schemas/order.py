from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class MenuItemOut(BaseModel):
    id: int
    name: str
    description: str | None
    category: str
    price: Decimal
    image_url: str | None
    is_available: bool


class OrderLineIn(BaseModel):
    menu_item_id: int
    quantity: int = Field(ge=1, le=20)


class OrderCreateIn(BaseModel):
    items: list[OrderLineIn] = Field(min_length=1, max_length=50)
    notes: str | None = Field(default=None, max_length=500)


class OrderItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    menu_item_id: int
    name: str
    quantity: int
    unit_price: Decimal
    line_total: Decimal


class HistoryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    from_status: str | None
    to_status: str
    changed_at: datetime


class OrderOut(BaseModel):
    id: int
    status: str
    priority: int
    tier_at_order: str
    total_amount: Decimal
    notes: str | None
    version: int
    created_at: datetime
    items: list[OrderItemOut]


class OrderDetailOut(OrderOut):
    history: list[HistoryOut]


class OrderPage(BaseModel):
    items: list[OrderOut]
    page: int
    page_size: int
    total: int
