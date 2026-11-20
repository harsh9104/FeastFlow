import uuid

from botocore.exceptions import BotoCoreError, ClientError
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import require_admin
from app.api.menu import menu_item_out
from app.db.session import get_db
from app.models.menu import MenuItem, Restaurant
from app.models.user import User
from app.schemas.menu import MenuItemCreate, MenuItemOut, MenuItemPatch
from app.services import storage_service

router = APIRouter(prefix="/api/admin/menu-items", tags=["admin"])

# First bytes of each allowed format, so a renamed .exe can't pass as a photo.
_MAGIC = {
    "image/jpeg": (b"\xff\xd8\xff",),
    "image/png": (b"\x89PNG\r\n\x1a\n",),
    "image/webp": (b"RIFF",),
}


def _get_item(db: Session, item_id: int) -> MenuItem:
    item = db.get(MenuItem, item_id)
    if item is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Menu item not found")
    return item


def _ensure_unique_name(db: Session, restaurant_id: int, name: str, item_id: int | None = None):
    conds = [MenuItem.restaurant_id == restaurant_id, func.lower(MenuItem.name) == name.lower()]
    if item_id is not None:
        conds.append(MenuItem.id != item_id)
    if db.scalar(select(MenuItem.id).where(*conds)):
        raise HTTPException(status.HTTP_409_CONFLICT, f"This restaurant already has '{name}'")


@router.post("", response_model=MenuItemOut, status_code=status.HTTP_201_CREATED)
def create_item(
    body: MenuItemCreate,
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Add a dish. It gets a placeholder picture straight away; upload a real photo
    with POST /{id}/image."""
    if db.get(Restaurant, body.restaurant_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Restaurant not found")
    data = body.model_dump()
    data["name"] = data["name"].strip()
    data["category"] = data["category"].strip()
    _ensure_unique_name(db, body.restaurant_id, data["name"])
    item = MenuItem(**data)
    db.add(item)
    db.commit()

    key = f"menu/{item.id}-{uuid.uuid4().hex[:8]}.svg"
    try:
        storage_service.upload_image(
            key, storage_service.placeholder_svg(item.name, item.id, item.category), "image/svg+xml"
        )
        item.image_key = key
        db.commit()
    except (BotoCoreError, ClientError):  # dish still works without a picture
        db.rollback()
    db.refresh(item)
    return menu_item_out(item)


@router.patch("/{item_id}", response_model=MenuItemOut)
def update_item(
    item_id: int,
    body: MenuItemPatch,
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    item = _get_item(db, item_id)
    changes = body.model_dump(exclude_unset=True)
    for field in ("name", "category"):
        if changes.get(field) is not None:
            changes[field] = changes[field].strip()
    if changes.get("name"):
        _ensure_unique_name(db, item.restaurant_id, changes["name"], item.id)
    for field, value in changes.items():
        if value is None and field != "description":
            continue  # only the description can be cleared
        setattr(item, field, value)
    db.commit()
    db.refresh(item)  # return what the database stored (e.g. price 65 -> 65.00)
    return menu_item_out(item)


@router.post("/{item_id}/image", response_model=MenuItemOut)
async def upload_image(
    item_id: int,
    file: UploadFile = File(...),
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    item = _get_item(db, item_id)
    ext = storage_service.ALLOWED_IMAGE_TYPES.get(file.content_type or "")
    if ext is None:
        raise HTTPException(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, "Use JPEG, PNG or WebP")
    data = await file.read(storage_service.MAX_IMAGE_BYTES + 1)
    if len(data) > storage_service.MAX_IMAGE_BYTES:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "Image must be under 2 MB")
    if not data.startswith(_MAGIC[file.content_type]):
        raise HTTPException(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, "File is not a valid image")

    # New key per upload, so browsers never show a cached old photo.
    key = f"menu/{item.id}-{uuid.uuid4().hex[:8]}.{ext}"
    storage_service.upload_image(key, data, file.content_type)
    item.image_key = key
    db.commit()
    return menu_item_out(item)
