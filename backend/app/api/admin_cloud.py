"""Admin Cloud & Cost panel: ASG instances, CPU, scaling activity, alarms and cost."""

from fastapi import APIRouter, Depends

from app.api.deps import require_admin
from app.models.user import User
from app.services import cloud_service

router = APIRouter(prefix="/api/admin", tags=["admin"])


@router.get("/cloud")
def cloud_overview(_: User = Depends(require_admin)):
    # Plain def: the boto3 calls block, so FastAPI runs this in its thread pool.
    return cloud_service.overview()
