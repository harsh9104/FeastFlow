from pathlib import Path

from fastapi import FastAPI, Request

from app.api import admin_dispatch, admin_menu, admin_users, auth, health, menu, orders
from app.core.config import get_settings
from app.core.instance import instance_id
from app.spa import mount_spa


def create_app() -> FastAPI:
    app = FastAPI(title="FeastFlow", version="0.1.0")

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
    # Last, so the catch-all never shadows an API route.
    mount_spa(app, Path(get_settings().static_dir))
    return app


app = create_app()
