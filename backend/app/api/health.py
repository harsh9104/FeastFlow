from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.instance import instance_id
from app.db.session import get_db

router = APIRouter(prefix="/api/health", tags=["health"])


@router.get("")
async def liveness():
    """Used by the ALB target group health check. No DB call, so a DB blip doesn't drain targets.
    async: runs on the event loop, so it answers even when every worker thread is busy."""
    return {"status": "ok", "instance": instance_id()}


@router.get("/ready")
def readiness(db: Session = Depends(get_db)):
    try:
        db.execute(text("SELECT 1"))
    except Exception as exc:  # noqa: BLE001
        return JSONResponse(status_code=503, content={"status": "unavailable", "db": str(exc)})
    return {"status": "ok", "db": "ok", "instance": instance_id()}
