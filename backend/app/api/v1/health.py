import time

from fastapi import APIRouter, Depends, Response
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.instance import get_instance_info
from app.db.session import get_db

router = APIRouter(prefix="/api", tags=["health"])
_started = time.time()


@router.get("/health")
def health():
    info = get_instance_info()
    return {
        "status": "ok",
        "version": get_settings().app_version,
        "instance_id": info["instance_id"],
        "az": info["az"],
        "uptime_s": int(time.time() - _started),
    }


@router.get("/health/ready")
def ready(response: Response, db: Session = Depends(get_db)):
    try:
        db.execute(text("SELECT 1"))
        return {"status": "ready", "db": "ok"}
    except Exception:
        response.status_code = 503
        return {"status": "not_ready", "db": "unreachable"}
