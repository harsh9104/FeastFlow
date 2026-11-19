from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class RestaurantOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    area: str
    cuisine: str
    is_open: bool


class MenuItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    restaurant_id: int
    name: str
    description: str | None
    category: str
    is_veg: bool
    price: Decimal
    is_available: bool
    image_url: str | None = None


class MenuItemPatch(BaseModel):
    price: Decimal | None = Field(default=None, gt=0, max_digits=10, decimal_places=2)
    is_available: bool | None = None
