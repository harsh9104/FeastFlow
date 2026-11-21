from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings


def _engine():
    s = get_settings()
    kwargs = {"pool_pre_ping": True, "pool_recycle": 1800}
    if not s.database_url.startswith("sqlite"):  # SQLite (tests, demo) has its own pooling
        kwargs |= {
            "pool_size": s.db_pool_size,
            "max_overflow": s.db_max_overflow,
            "pool_timeout": s.db_pool_timeout,
        }
    return create_engine(s.database_url, **kwargs)


engine = _engine()
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_db() -> Iterator[Session]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
