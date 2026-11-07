import time
from functools import lru_cache

from app.core.config import get_settings

_cache: dict[str, tuple[float, str]] = {}
_TTL = 600


@lru_cache
def _client():
    import boto3

    s = get_settings()
    return boto3.client("s3", region_name=s.aws_region)


def image_url(key: str | None) -> str | None:
    """Pre-signed S3 URL (cached 10 min). None when no bucket is configured (local dev)."""
    bucket = get_settings().s3_bucket
    if not key or not bucket:
        return None
    hit = _cache.get(key)
    if hit and hit[0] > time.time():
        return hit[1]
    url = _client().generate_presigned_url(
        "get_object", Params={"Bucket": bucket, "Key": key}, ExpiresIn=_TTL * 2
    )
    _cache[key] = (time.time() + _TTL, url)
    return url
