from pathlib import Path

from fastapi import FastAPI, Request

from app.api import (
    admin_cloud,
    admin_dispatch,
    admin_festival,
    admin_menu,
    admin_users,
    auth,
    health,
    menu,
    orders,
)
from app.core.admission import AdmissionLimit
from app.core.config import get_settings
from app.core.instance import instance_id
from app.spa import mount_spa


def create_app() -> FastAPI:
    app = FastAPI(title="FeastFlow", version="0.1.0")
    s = get_settings()
    # Added first so it sits inside served_by: busy (503) answers still carry X-Served-By.
    app.add_middleware(AdmissionLimit, limit=s.api_max_concurrency, timeout=s.api_queue_timeout)

    @app.middleware("http")
    async def served_by(request: Request, call_next):
        response = await call_next(request)
        response.headers["X-Served-By"] = instance_id()
        return response

    app.include_router(health.router)
    app.include_router(auth.router)
    app.include_router(admin_users.router)
    app.include_router(menu.router)
    app.include_router(orders.router)
    app.include_router(admin_menu.router)
    app.include_router(admin_dispatch.router)
    app.include_router(admin_festival.router)
    app.include_router(admin_cloud.router)
    # Last, so the catch-all never shadows an API route.
    mount_spa(app, Path(s.static_dir))
    return app


app = create_app()
