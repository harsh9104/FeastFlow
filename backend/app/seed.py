"""Run on container start after migrations: `python -m app.seed`."""

import logging

from sqlalchemy import select

from app.core.config import get_settings
from app.db.session import SessionLocal
from app.models.menu import MenuItem
from app.services.storage_service import safe_seed_placeholder_images
from app.services.user_service import ensure_admin, ensure_test_users

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s seed %(message)s")


def main() -> None:
    with SessionLocal() as db:
        created = ensure_admin(db)
        logging.info("admin user %s", "created" if created else "already present")
        n = ensure_test_users(db)
        logging.info(
            "load-test customers: %d created, login %s",
            n,
            "enabled" if get_settings().loadtest_password else "disabled (LOADTEST_PASSWORD unset)",
        )
        if get_settings().seed_images:
            n = safe_seed_placeholder_images(db.scalars(select(MenuItem)).all())
            logging.info("uploaded %d placeholder food images", n)


if __name__ == "__main__":
    main()
