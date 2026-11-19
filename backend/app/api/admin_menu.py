import uuid

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from app.api.deps import require_admin
from app.api.menu import menu_item_out
from app.db.session import get_db
from app.models.menu import MenuItem
from app.models.user import User
from app.schemas.menu import MenuItemOut, MenuItemPatch
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


@router.patch("/{item_id}", response_model=MenuItemOut)
def update_item(
    item_id: int,
    body: MenuItemPatch,
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    item = _get_item(db, item_id)
    for field, value in body.model_dump(exclude_none=True).items():
        setattr(item, field, value)
    db.commit()
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
