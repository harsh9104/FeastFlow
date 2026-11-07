import logging
import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.api.v1 import (
    admin_orders,
    admin_users,
    auth,
    cloud,
    costs_reports,
    health,
    load_tests,
    menu,
    orders,
    sla,
    users,
)
from app.core.config import get_settings
from app.core.errors import register_error_handlers
from app.core.instance import get_instance_info
from app.core.logging import setup_logging
from app.services.metrics_collector import collector

access_log = logging.getLogger("app.access")


def create_app() -> FastAPI:
    settings = get_settings()
    setup_logging(settings.log_level)
    prod = settings.env == "production"
    local_metrics = settings.metrics_provider == "local"

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        started = local_metrics and settings.env != "test"
        if started:
            collector.start()
        yield
        if started:
            collector.stop()

    app = FastAPI(
        lifespan=lifespan,
        title="FeastFlow",
        version=settings.app_version,
        docs_url=None if prod else "/api/docs",
        openapi_url=None if prod else "/api/openapi.json",
    )
    register_error_handlers(app)

    @app.middleware("http")
    async def request_context(request: Request, call_next):
        rid = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        request.state.request_id = rid
        start = time.perf_counter()
        response = await call_next(request)
        info = get_instance_info()
        response.headers["X-Request-ID"] = rid
        response.headers["X-Served-By"] = f"{info['instance_id']} ({info['az']})"
        ms = (time.perf_counter() - start) * 1000
        if request.url.path != "/api/health":
            if local_metrics:
                collector.record(response.status_code, ms)
            access_log.info(
                "request",
                extra={
                    "extra_fields": {
                        "request_id": rid,
                        "method": request.method,
                        "path": request.url.path,
                        "status": response.status_code,
                        "ms": round(ms, 1),
                    }
                },
            )
        return response

    app.include_router(health.router)
    app.include_router(auth.router)
    app.include_router(users.router)
    app.include_router(menu.router)
    app.include_router(orders.router)
    app.include_router(admin_users.router)
    app.include_router(admin_orders.router)
    app.include_router(load_tests.router)
    app.include_router(cloud.router)
    app.include_router(costs_reports.router)
    app.include_router(sla.router)
    _mount_spa(app)
    return app


def _mount_spa(app: FastAPI) -> None:
    """Serve the built React app; unknown non-API paths fall back to index.html."""
    static = Path(__file__).parent / "static"
    index = static / "index.html"
    if not index.is_file():
        return
    if (static / "assets").is_dir():
        app.mount("/assets", StaticFiles(directory=static / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str):
        if path.startswith("api/"):
            raise HTTPException(404, "Not found")
        target = (static / path).resolve()
        if path and target.is_file() and static.resolve() in target.parents:
            return FileResponse(target)
        return FileResponse(index)


app = create_app()
