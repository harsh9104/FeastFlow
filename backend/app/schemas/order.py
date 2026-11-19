from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class OrderLineIn(BaseModel):
    menu_item_id: int
    quantity: int = Field(ge=1)


class OrderIn(BaseModel):
    items: list[OrderLineIn] = Field(min_length=1)
    delivery_address: str = Field(min_length=5, max_length=255)


class OrderItemOut(BaseModel):
    menu_item_id: int
    name: str
    quantity: int
    unit_price: Decimal


class OrderEventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    status: str
    note: str | None
    created_at: datetime


class OrderOut(BaseModel):
    id: int
    status: str
    priority: int
    is_prime: bool
    restaurant_id: int
    restaurant_name: str
    total_amount: Decimal
    delivery_address: str
    created_at: datetime
    customer_name: str | None = None
    partner_name: str | None = None
    partner_phone: str | None = None
    items: list[OrderItemOut]
    events: list[OrderEventOut]


class OrderListOut(BaseModel):
    total: int
    items: list[OrderOut]
