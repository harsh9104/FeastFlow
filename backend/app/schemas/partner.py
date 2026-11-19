from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class PartnerOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    phone: str
    status: str
    deliveries_count: int
    current_order_id: int | None = None
    updated_at: datetime | None = None


class PartnerIn(BaseModel):
    name: str = Field(min_length=2, max_length=100)
    phone: str = Field(pattern=r"^\+?[0-9]{8,15}$")


class PartnerStatusIn(BaseModel):
    # BUSY is set only by the worker when it assigns an order.
    status: Literal["AVAILABLE", "OFFLINE"]
