from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.menu import MenuItem, Restaurant
from app.schemas.menu import MenuItemOut, RestaurantOut
from app.services import order_service, storage_service

router = APIRouter(prefix="/api/restaurants", tags=["menu"])


def menu_item_out(item: MenuItem) -> MenuItemOut:
    out = MenuItemOut.model_validate(item)
    out.image_url = storage_service.image_url(item.image_key)
    return out


@router.get("", response_model=list[RestaurantOut])
def restaurants(db: Session = Depends(get_db)):
    return order_service.list_restaurants(db)


@router.get("/{restaurant_id}/menu", response_model=list[MenuItemOut])
def menu(restaurant_id: int, db: Session = Depends(get_db)):
    if db.get(Restaurant, restaurant_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Restaurant not found")
    items = db.scalars(
        select(MenuItem)
        .where(MenuItem.restaurant_id == restaurant_id)
        .order_by(MenuItem.category, MenuItem.id)
    )
    return [menu_item_out(i) for i in items]
