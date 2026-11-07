import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

log = logging.getLogger("app.errors")


class AppError(Exception):
    def __init__(self, status_code: int, code: str, message: str, details=None):
        self.status_code = status_code
        self.code = code
        self.message = message
        self.details = details


def _body(request: Request, code: str, message: str, details=None) -> dict:
    return {
        "error": {"code": code, "message": message, "details": details},
        "request_id": getattr(request.state, "request_id", None),
    }


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def _app_error(request: Request, exc: AppError):
        return JSONResponse(
            _body(request, exc.code, exc.message, exc.details), status_code=exc.status_code
        )

    @app.exception_handler(StarletteHTTPException)
    async def _http_error(request: Request, exc: StarletteHTTPException):
        codes = {401: "UNAUTHORIZED", 403: "FORBIDDEN", 404: "NOT_FOUND", 405: "METHOD_NOT_ALLOWED"}
        return JSONResponse(
            _body(request, codes.get(exc.status_code, "HTTP_ERROR"), str(exc.detail)),
            status_code=exc.status_code,
            headers=getattr(exc, "headers", None),
        )

    @app.exception_handler(RequestValidationError)
    async def _validation(request: Request, exc: RequestValidationError):
        details = [{"loc": list(e["loc"]), "msg": e["msg"]} for e in exc.errors()]
        return JSONResponse(
            _body(request, "VALIDATION_ERROR", "Request validation failed", details),
            status_code=422,
        )

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception):
        log.exception("unhandled error")
        return JSONResponse(
            _body(request, "INTERNAL_ERROR", "Internal server error"), status_code=500
        )
