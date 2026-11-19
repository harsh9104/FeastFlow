"""Run on container start after migrations: `python -m app.seed`."""

import logging

from app.db.session import SessionLocal
from app.services.user_service import ensure_admin

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s seed %(message)s")


def main() -> None:
    with SessionLocal() as db:
        created = ensure_admin(db)
    logging.info("admin user %s", "created" if created else "already present")


if __name__ == "__main__":
    main()
