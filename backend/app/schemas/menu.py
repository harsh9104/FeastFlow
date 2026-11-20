from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class RestaurantOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    area: str
    cuisine: str
    is_open: bool
    rating: Decimal
    delivery_minutes: int
    cost_for_two: int
    offer: str | None


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
    is_bestseller: bool
    image_url: str | None = None


_PRICE = {"gt": 0, "le": 99999, "max_digits": 7, "decimal_places": 2}


class MenuItemCreate(BaseModel):
    restaurant_id: int
    name: str = Field(min_length=2, max_length=120)
    description: str | None = Field(default=None, max_length=500)
    category: str = Field(min_length=2, max_length=50)
    is_veg: bool = True
    price: Decimal = Field(**_PRICE)
    is_bestseller: bool = False
    is_available: bool = True


class MenuItemPatch(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=120)
    description: str | None = Field(default=None, max_length=500)
    category: str | None = Field(default=None, min_length=2, max_length=50)
    is_veg: bool | None = None
    price: Decimal | None = Field(default=None, **_PRICE)
    is_bestseller: bool | None = None
    is_available: bool | None = None
