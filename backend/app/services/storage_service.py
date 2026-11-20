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


# Warm two-tone backgrounds, picked per dish so neighbouring cards differ.
_GRADIENTS = [
    ("#ff9a3c", "#ff5e3a"), ("#f7b733", "#fc4a1a"), ("#f857a6", "#ff5858"),
    ("#ffb347", "#ffcc33"), ("#56ab2f", "#a8e063"), ("#ee9ca7", "#ffdde1"),
    ("#ff7e5f", "#feb47b"), ("#e65c00", "#f9d423"),
]

# First keyword found in the dish name/category picks the emoji.
# Specific dishes come before generic words ("Masala Dosa" is a dosa, not a curry).
_DISH_EMOJI = [
    ("dosa", "🥞"), ("idli", "🍥"), ("vada", "🍩"), ("biryani", "🍛"), ("pizza", "🍕"),
    ("burger", "🍔"), ("noodle", "🍜"), ("momo", "🥟"), ("chai", "🍵"), ("coffee", "☕"),
    ("naan", "🫓"), ("roti", "🫓"), ("paratha", "🫓"), ("dal", "🍲"),
    ("curry", "🍛"), ("masala", "🍛"), ("paneer", "🍛"), ("jamun", "🍮"),
    ("dessert", "🍨"), ("kulfi", "🍨"), ("ice", "🍨"),
    ("cake", "🍰"), ("coffee", "☕"), ("tea", "🍵"), ("chai", "🍵"), ("shake", "🥤"),
    ("lassi", "🥛"), ("juice", "🧃"), ("beverage", "🥤"), ("noodle", "🍜"), ("hakka", "🍜"),
    ("manchurian", "🥘"), ("chilli", "🌶️"), ("chicken", "🍗"), ("fried rice", "🍚"),
    ("rice", "🍚"), ("spring roll", "🌯"), ("roll", "🌯"), ("momo", "🥟"), ("pizza", "🍕"),
    ("burger", "🍔"), ("fries", "🍟"), ("sandwich", "🥪"), ("pasta", "🍝"), ("salad", "🥗"),
    ("soup", "🍲"), ("egg", "🍳"), ("fish", "🐟"), ("prawn", "🍤"), ("taco", "🌮"),
]


def dish_emoji(name: str, category: str = "") -> str:
    text = f"{name} {category}".lower()
    return next((e for key, e in _DISH_EMOJI if key in text), "🍽️")


def placeholder_svg(name: str, seed: int, category: str = "") -> bytes:
    """Food-style illustration (dish emoji on a plate over a warm gradient) until a
    real photo is uploaded from the admin Menu page."""
    a, b = _GRADIENTS[seed % len(_GRADIENTS)]
    emoji = html.escape(dish_emoji(name, category))
    return f"""<svg xmlns="http://www.w3.org/2000/svg"
  width="480" height="360" viewBox="0 0 480 360">
<defs>
  <linearGradient id="bg" x1="0" y1="0" x2="1" y2="1">
    <stop offset="0" stop-color="{a}"/><stop offset="1" stop-color="{b}"/>
  </linearGradient>
  <radialGradient id="plate" cx="0.5" cy="0.45" r="0.6">
    <stop offset="0" stop-color="#ffffff"/><stop offset="0.85" stop-color="#f3f0ea"/>
    <stop offset="1" stop-color="#e2ddd4"/>
  </radialGradient>
</defs>
<rect width="480" height="360" fill="url(#bg)"/>
<circle cx="70" cy="60" r="90" fill="#fff" opacity="0.12"/>
<circle cx="430" cy="320" r="120" fill="#fff" opacity="0.10"/>
<ellipse cx="240" cy="208" rx="150" ry="40" fill="#000" opacity="0.15"/>
<ellipse cx="240" cy="192" rx="150" ry="118" fill="url(#plate)"/>
<ellipse cx="240" cy="192" rx="118" ry="90" fill="none" stroke="#e8e2d8" stroke-width="3"/>
<text x="240" y="242" font-size="150" text-anchor="middle"
  font-family="Segoe UI Emoji, Apple Color Emoji, Noto Color Emoji, sans-serif">{emoji}</text>
</svg>""".encode()


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
        upload_image(
            item.image_key,
            placeholder_svg(item.name, item.id, item.category),
            "image/svg+xml",
        )
        uploaded += 1
    return uploaded


def safe_seed_placeholder_images(items) -> int:
    try:
        return seed_placeholder_images(items)
    except (BotoCoreError, ClientError) as exc:
        log.warning("image seeding skipped: %s", exc)
        return 0
