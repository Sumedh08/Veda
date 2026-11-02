import logging
import re
import uuid

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.exc import (
    DBAPIError,
    InterfaceError,
    OperationalError,
    SQLAlchemyError,
)
from sqlalchemy.exc import (
    TimeoutError as SQLAlchemyTimeoutError,
)

from app.api.routes import health_router, router
from app.config import settings
from app.logging_privacy import HttpxRequestLogFilter
from app.request_size import RequestBodyLimitMiddleware

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger(__name__)
httpx_logger = logging.getLogger("httpx")
if not any(isinstance(filter_, HttpxRequestLogFilter) for filter_ in httpx_logger.filters):
    httpx_logger.addFilter(HttpxRequestLogFilter())
REQUEST_ID_PATTERN = re.compile(r"[A-Za-z0-9._:-]{1,128}\Z")
app = FastAPI(title="Veda API", version="0.1.0", docs_url="/api/docs", redoc_url=None)
app.add_middleware(
    RequestBodyLimitMiddleware,
    max_body_bytes=settings.max_request_body_bytes,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-Request-ID"],
    expose_headers=["Content-Disposition", "X-Request-ID"],
)


def _security_response_headers() -> dict[str, str]:
    return {
        "X-Content-Type-Options": "nosniff",
        "Referrer-Policy": "strict-origin-when-cross-origin",
        "X-Frame-Options": "DENY",
        "Content-Security-Policy": "default-src 'none'; frame-ancestors 'none'",
    }


def _unhandled_error_headers(request: Request, request_id: str | None) -> dict[str, str]:
    headers = _security_response_headers()
    if request_id:
        headers["X-Request-ID"] = request_id
    origin = request.headers.get("origin", "")
    if origin in settings.cors_origins:
        headers.update(
            {
                "Access-Control-Allow-Origin": origin,
                "Access-Control-Allow-Credentials": "true",
                "Access-Control-Expose-Headers": "Content-Disposition, X-Request-ID",
                "Vary": "Origin",
            }
        )
    return headers


def _unexpected_error_response(
    request: Request,
    request_id: str,
    exc: Exception,
) -> JSONResponse:
    logger.error(
        "unhandled request failed request_id=%s error_class=%s",
        request_id,
        type(exc).__name__,
    )
    return JSONResponse(
        status_code=500,
        content={
            "error": {
                "code": "internal_error",
                "message": "The request could not be completed.",
                "request_id": request_id,
            }
        },
        headers=_unhandled_error_headers(request, request_id),
    )


@app.middleware("http")
async def add_request_id_and_security_headers(request: Request, call_next):
    supplied_id = request.headers.get("x-request-id", "")
    request_id = supplied_id if REQUEST_ID_PATTERN.fullmatch(supplied_id) else str(uuid.uuid4())
    request.state.request_id = request_id
    try:
        response = await call_next(request)
    except Exception as exc:
        # Return before ServerErrorMiddleware can re-raise and log raw exception details.
        return _unexpected_error_response(request, request_id, exc)
    response.headers["X-Request-ID"] = request_id
    for name, value in _security_response_headers().items():
        response.headers[name] = value
    return response


@app.exception_handler(RequestValidationError)
async def validation_error_handler(request: Request, exc: RequestValidationError):
    return JSONResponse(
        status_code=422,
        content={
            "error": {
                "code": "validation_error",
                "message": "The request did not pass validation.",
                "request_id": getattr(request.state, "request_id", None),
            }
        },
    )


@app.exception_handler(SQLAlchemyError)
async def database_error_handler(request: Request, exc: SQLAlchemyError):
    request_id = getattr(request.state, "request_id", None)
    unavailable = isinstance(exc, (OperationalError, InterfaceError, SQLAlchemyTimeoutError)) or (
        isinstance(exc, DBAPIError) and exc.connection_invalidated
    )
    status_code = 503 if unavailable else 500
    code = "storage_unavailable" if unavailable else "storage_error"
    message = (
        "Storage is temporarily unavailable. Please retry."
        if unavailable
        else "The storage operation could not be completed."
    )
    logger.error(
        "database request failed request_id=%s error_class=%s",
        request_id,
        type(exc).__name__,
    )
    return JSONResponse(
        status_code=status_code,
        content={
            "error": {
                "code": code,
                "message": message,
                "request_id": request_id,
            }
        },
    )


app.include_router(health_router, prefix="/api/v1")
app.include_router(router, prefix="/api/v1")
