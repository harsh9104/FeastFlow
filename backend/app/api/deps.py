import jwt
from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.core.security import decode_token
from app.db.session import get_db
from app.models.user import User

_bearer = HTTPBearer(auto_error=False)


def get_current_user(
    creds: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: Session = Depends(get_db),
) -> User:
    if creds is None:
        raise AppError(401, "UNAUTHORIZED", "Missing bearer token")
    try:
        payload = decode_token(creds.credentials)
        user = db.get(User, int(payload["sub"]))
    except (jwt.PyJWTError, KeyError, ValueError):
        raise AppError(401, "UNAUTHORIZED", "Invalid or expired token") from None
    if user is None:
        raise AppError(401, "UNAUTHORIZED", "User no longer exists")
    return user


def require_admin(user: User = Depends(get_current_user)) -> User:
    if user.role != "ADMIN":
        raise AppError(403, "FORBIDDEN", "Admin role required")
    return user


def require_customer(user: User = Depends(get_current_user)) -> User:
    if user.role != "CUSTOMER":
        raise AppError(403, "FORBIDDEN", "Customer role required")
    return user
