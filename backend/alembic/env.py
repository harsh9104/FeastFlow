from sqlalchemy import text

from alembic import context
from app import models  # noqa: F401
from app.db.base import Base
from app.db.session import engine

target_metadata = Base.metadata
LOCK_ID = 727274  # advisory lock: only one instance migrates at a time


def run_migrations_online() -> None:
    with engine.connect() as conn:
        conn.execute(text("SELECT pg_advisory_lock(:id)"), {"id": LOCK_ID})
        conn.commit()
        try:
            context.configure(connection=conn, target_metadata=target_metadata)
            with context.begin_transaction():
                context.run_migrations()
            conn.commit()
        finally:
            conn.execute(text("SELECT pg_advisory_unlock(:id)"), {"id": LOCK_ID})
            conn.commit()


run_migrations_online()
