"""Login rate limiting: too many FAILED logins per email or per client IP within a window -> 429.

Stored in Postgres so the limit holds across every app instance behind the ALB. Successful logins
are never counted, so Locust (many logins from one IP, all correct) is not affected. The check runs
before bcrypt, so a locked-out attacker cannot burn CPU either.
"""

import logging
import math
from datetime import timedelta

from fastapi import Request
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import AppError
from app.models.login_failure import LoginFailure

log = logging.getLogger("app.auth")


def client_ip(request: Request) -> str:
    s = get_settings()
    if s.trust_forwarded_for:
        # The ALB appends the real peer address as the LAST entry; anything before it is client-supplied.
        fwd = request.headers.get("x-forwarded-for", "")
        last = fwd.rsplit(",", 1)[-1].strip()
        if last:
            return last[:64]
    return (request.client.host if request.client else "unknown")[:64]


def _retry_after(db: Session, column, value: str, limit: int, since) -> int | None:
    """Seconds until fewer than `limit` failures remain in the window, or None if not limited."""
    times = db.scalars(
        select(LoginFailure.created_at)
        .where(column == value, LoginFailure.created_at > since)
        .order_by(LoginFailure.created_at.desc())
        .limit(limit)
    ).all()
    if len(times) < limit:
        return None
    # The oldest of the last `limit` failures leaves the window at times[-1] + window,
    # and since = now - window, so the wait is times[-1] - since.
    return (times[-1] - since).total_seconds()


def check(db: Session, email: str, ip: str) -> None:
    s = get_settings()
    now = db.scalar(select(func.now()))
    since = now - timedelta(seconds=s.login_window_s)
    waits = [
        w
        for w in (
            _retry_after(db, LoginFailure.email, email, s.login_max_failures_per_email, since),
            _retry_after(db, LoginFailure.ip, ip, s.login_max_failures_per_ip, since),
        )
        if w is not None
    ]
    if waits:
        wait = max(1, math.ceil(max(waits)))
        log.warning("login rate-limited email=%s ip=%s retry_after=%ss", email, ip, wait)
        minutes = math.ceil(wait / 60)
        raise AppError(
            429,
            "TOO_MANY_ATTEMPTS",
            f"Too many failed login attempts. Try again in {minutes} minute{'s' if minutes > 1 else ''}.",
            {"retry_after_s": wait},
            headers={"Retry-After": str(wait)},
        )


def record_failure(db: Session, email: str, ip: str) -> None:
    window = timedelta(seconds=get_settings().login_window_s)
    db.add(LoginFailure(email=email, ip=ip))
    db.execute(delete(LoginFailure).where(LoginFailure.created_at < func.now() - window))  # prune
    db.commit()


def clear_email(db: Session, email: str) -> None:
    """A correct password resets that account's counter (the IP counter keeps running)."""
    db.execute(delete(LoginFailure).where(LoginFailure.email == email))
    db.commit()
