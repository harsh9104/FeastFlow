"""Food images in a private S3 bucket. The browser gets short-lived presigned URLs,
so the bucket never has to be public."""

import html
import logging

from botocore.exceptions import BotoCoreError, ClientError

from app.core import aws
from app.core.config import get_settings

log = logging.getLogger(__name__)

ALLOWED_IMAGE_TYPES = {"image/jpeg": "jpg", "image/png": "png", "image/webp": "webp"}
MAX_IMAGE_BYTES = 2 * 1024 * 1024


def image_url(key: str | None) -> str | None:
    if not key:
        return None
    s = get_settings()
    return aws.s3_presigner().generate_presigned_url(
        "get_object",
        Params={"Bucket": s.s3_bucket, "Key": key},
        ExpiresIn=s.image_url_ttl_seconds,
    )


def upload_image(key: str, data: bytes, content_type: str) -> None:
    aws.s3().put_object(
        Bucket=get_settings().s3_bucket,
        Key=key,
        Body=data,
        ContentType=content_type,
        CacheControl="public, max-age=86400",
    )


_PALETTE = ["#e4572e", "#f3a712", "#29335c", "#669bbc", "#2a9d8f", "#8f2d56", "#6a994e"]


def placeholder_svg(name: str, seed: int) -> bytes:
    """Simple coloured card with the dish name, until real photos are uploaded."""
    bg = _PALETTE[seed % len(_PALETTE)]
    label = html.escape(name)
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" width="480" height="320" viewBox="0 0 480 320">'
        f'<rect width="480" height="320" fill="{bg}"/>'
        '<circle cx="240" cy="130" r="62" fill="#fff" opacity="0.18"/>'
        '<text x="240" y="148" font-size="56" text-anchor="middle">🍽</text>'
        f'<text x="240" y="250" font-family="sans-serif" font-size="28" fill="#fff" '
        f'text-anchor="middle">{label}</text></svg>'
    ).encode()


def seed_placeholder_images(items) -> int:
    """Upload a placeholder for each menu item whose image is missing. Returns count uploaded."""
    bucket = get_settings().s3_bucket
    uploaded = 0
    for item in items:
        if not item.image_key:
            continue
        try:
            aws.s3().head_object(Bucket=bucket, Key=item.image_key)
            continue  # already there (a real photo may have replaced the placeholder)
        except ClientError as exc:
            if exc.response["Error"]["Code"] not in ("404", "NoSuchKey", "NotFound"):
                raise
        upload_image(item.image_key, placeholder_svg(item.name, item.id), "image/svg+xml")
        uploaded += 1
    return uploaded


def safe_seed_placeholder_images(items) -> int:
    try:
        return seed_placeholder_images(items)
    except (BotoCoreError, ClientError) as exc:
        log.warning("image seeding skipped: %s", exc)
        return 0
