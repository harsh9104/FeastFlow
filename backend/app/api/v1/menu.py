from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.errors import AppError
from app.db.session import get_db
from app.models.order import MenuItem
from app.models.user import User
from app.schemas.order import MenuItemOut
from app.services.storage_service import image_url

router = APIRouter(prefix="/api/v1/menu", tags=["menu"])


def _out(m: MenuItem) -> MenuItemOut:
    return MenuItemOut(
        id=m.id,
        name=m.name,
        description=m.description,
        category=m.category,
        price=m.price,
        image_url=image_url(m.image_key),
        is_available=m.is_available,
    )


@router.get("", response_model=list[MenuItemOut])
def list_menu(_: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return [_out(m) for m in db.scalars(select(MenuItem).order_by(MenuItem.category, MenuItem.id))]


@router.get("/{item_id}", response_model=MenuItemOut)
def get_item(item_id: int, _: User = Depends(get_current_user), db: Session = Depends(get_db)):
    m = db.get(MenuItem, item_id)
    if m is None:
        raise AppError(404, "NOT_FOUND", "Menu item not found")
    return _out(m)
