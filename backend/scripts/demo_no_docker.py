"""Run the whole app on your machine WITHOUT Docker (development/demo only).

    cd backend
    .venv/Scripts/python scripts/demo_no_docker.py          # Windows
    .venv/bin/python scripts/demo_no_docker.py              # macOS / Linux

Then open http://127.0.0.1:8000 (admin: admin@feastflow.app / Admin@12345).

What's real: the API, the worker (SQS consumer + timers + rider assignment), the
React build, the festival simulator. What's faked: MySQL is a local SQLite file and
SQS/SNS/S3 are moto's in-memory mocks, so food images don't load in the browser and
no emails are sent. Timers are shortened so orders finish in ~20 s.
Use `docker compose up` for the real stack (MySQL + LocalStack).

Load test against it (needs `pip install locust==2.32.4` in some environment):
    locust -f ../loadtest/locustfile.py --host http://127.0.0.1:8000
with LOADTEST_PASSWORD=Festival-local-only-1 set in that shell.
"""

import importlib.util
import os
import sys
import threading
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
REPO = BACKEND.parent
DB_FILE = BACKEND / ".demo.sqlite3"

os.environ.update(
    DATABASE_URL=f"sqlite:///{DB_FILE.as_posix()}?check_same_thread=false",
    AWS_ACCESS_KEY_ID="testing",
    AWS_SECRET_ACCESS_KEY="testing",
    AWS_SESSION_TOKEN="testing",
    AWS_DEFAULT_REGION="us-east-1",
    AWS_ENDPOINT_URL="",
    S3_PUBLIC_ENDPOINT_URL="",
    STATIC_DIR=str(REPO / "frontend" / "dist"),
    ADMIN_EMAIL="admin@feastflow.app",
    ADMIN_PASSWORD="Admin@12345",
    JWT_SECRET="demo-only-secret",
    LOADTEST_PASSWORD=os.environ.get("LOADTEST_PASSWORD") or "Festival-local-only-1",
    LOCUST_URL=os.environ.get("LOCUST_URL") or "http://127.0.0.1:8089",
)
for key, value in {"CONFIRM_SECONDS": "2", "PREP_SECONDS": "6", "DELIVERY_SECONDS": "10"}.items():
    os.environ.setdefault(key, value)
sys.path.insert(0, str(BACKEND))

from moto import mock_aws  # noqa: E402

mock_aws().start()

import uvicorn  # noqa: E402
from sqlalchemy import select  # noqa: E402

from app.core import aws  # noqa: E402
from app.core.config import get_settings  # noqa: E402
from app.db.base import Base  # noqa: E402
from app.db.session import SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402
from app.models import DeliveryPartner, MenuItem, Restaurant  # noqa: E402
from app.services.storage_service import seed_placeholder_images  # noqa: E402
from app.services.user_service import ensure_admin, ensure_test_users  # noqa: E402
from worker.main import run_consumer, run_ticker  # noqa: E402


def load_migration(name: str):
    spec = importlib.util.spec_from_file_location(name, BACKEND / "alembic" / "versions" / name)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def setup() -> None:
    s = get_settings()
    for q in (s.sqs_prime_queue, s.sqs_standard_queue):
        aws.sqs().create_queue(QueueName=q)
    aws.s3().create_bucket(Bucket=s.s3_bucket)
    aws.topic_arn()

    DB_FILE.unlink(missing_ok=True)  # fresh data every start
    Base.metadata.create_all(engine)
    menu = load_migration("0003_seed_menu.py")
    partners = load_migration("0004_delivery_partners.py")
    with SessionLocal() as db:
        for rid, name, area, cuisine in menu.RESTAURANTS:
            db.add(Restaurant(id=rid, name=name, area=area, cuisine=cuisine))
        for iid, rid, name, cat, veg, price, desc in menu.ITEMS:
            db.add(MenuItem(id=iid, restaurant_id=rid, name=name, category=cat, is_veg=veg,
                            price=price, description=desc, image_key=f"menu/{iid}.svg"))
        for i, first in enumerate(partners.FIRST):
            last = partners.LAST[i % len(partners.LAST)]
            db.add(DeliveryPartner(name=f"{first} {last}", phone=f"+91900000{i + 1:04d}"))
        db.commit()
        ensure_admin(db)
        ensure_test_users(db)
        seed_placeholder_images(db.scalars(select(MenuItem)).all())


if __name__ == "__main__":
    if not (REPO / "frontend" / "dist" / "index.html").is_file():
        print("Build the UI first: cd frontend && npm install && npm run build", file=sys.stderr)
    setup()
    stop = threading.Event()
    for target in (run_consumer, run_ticker):
        threading.Thread(target=target, args=(stop,), daemon=True).start()
    print("FeastFlow demo on http://127.0.0.1:8000  (admin@feastflow.app / Admin@12345)")
    uvicorn.run(app, host="127.0.0.1", port=8000, log_level="warning")
