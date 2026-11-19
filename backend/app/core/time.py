from datetime import UTC, datetime


def utcnow() -> datetime:
    """Naive UTC timestamp. MySQL DATETIME has no timezone, so everything is stored as UTC."""
    return datetime.now(UTC).replace(tzinfo=None)
