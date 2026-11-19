from fastapi import FastAPI, Request

from app.api import admin_menu, admin_users, auth, health, menu, orders
from app.core.instance import instance_id


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
    return app


app = create_app()
