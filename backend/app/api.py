import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from opentelemetry import trace
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.sdk.trace import TracerProvider
from redis import Redis
from redis.exceptions import RedisError
from sqlalchemy import text
from sqlalchemy.exc import InterfaceError, OperationalError
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.config import get_settings
from app.errors import AppError
from app.http import SessionDep
from app.routers import batches, documents, proposals
from app.telemetry import configure_telemetry

logger = logging.getLogger(__name__)


class BodyLimitMiddleware:
    """Cap the complete body before multipart parsing/spooling, including chunked uploads."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope["method"] in {"GET", "HEAD", "OPTIONS"}:
            await self.app(scope, receive, send)
            return
        messages: list[Message] = []
        size = 0
        while True:
            message = await receive()
            messages.append(message)
            size += len(message.get("body", b""))
            if size > 11 * 1024 * 1024:
                await JSONResponse(
                    {"error": {"code": "FILE_TOO_LARGE", "message": "La petición supera 11 MiB"}},
                    status_code=413,
                )(scope, receive, send)
                return
            if not message.get("more_body", False):
                break
        iterator = iter(messages)

        async def replay() -> Message:
            return next(iterator, None) or await receive()

        await self.app(scope, replay, send)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    get_settings().upload_dir.mkdir(parents=True, exist_ok=True)
    configure_telemetry("andinarag-api")
    yield
    provider = trace.get_tracer_provider()
    if isinstance(provider, TracerProvider):
        provider.shutdown()


app = FastAPI(title="AndinaRAG", version="0.1.0", lifespan=lifespan)
app.add_middleware(BodyLimitMiddleware)
FastAPIInstrumentor.instrument_app(app, excluded_urls="health/live,health/ready")


@app.exception_handler(AppError)
async def application_error(request: Request, exc: AppError) -> JSONResponse:
    return JSONResponse({"error": exc.payload()}, status_code=exc.status)


@app.exception_handler(RequestValidationError)
async def validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
    return JSONResponse(
        {
            "error": {
                "code": "VALIDATION_ERROR",
                "message": "Revisa los campos",
                "fields": [list(error["loc"]) for error in exc.errors()],
            }
        },
        status_code=422,
    )


@app.exception_handler(OperationalError)
@app.exception_handler(InterfaceError)
async def database_error(request: Request, exc: Exception) -> JSONResponse:
    logger.error("database_unavailable")
    return JSONResponse(
        {
            "error": {
                "code": "DATABASE_UNAVAILABLE",
                "message": "PostgreSQL no está disponible; vuelve a intentar",
            }
        },
        status_code=503,
    )


@app.middleware("http")
async def trace_header(request: Request, call_next: Any) -> Any:
    response = await call_next(request)
    context = trace.get_current_span().get_span_context()
    if context.is_valid:
        response.headers["X-Trace-ID"] = format(context.trace_id, "032x")
    logger.info(
        "http_request",
        extra={"method": request.method, "path": request.url.path, "status": response.status_code},
    )
    return response


@app.get("/api/v1/health/live")
def health_live() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/v1/health/ready")
def health_ready(session: SessionDep) -> dict[str, str]:
    session.execute(text("SELECT 1"))
    try:
        Redis.from_url(get_settings().redis_url, socket_connect_timeout=2, socket_timeout=2).ping()
    except RedisError:
        raise AppError("BROKER_UNAVAILABLE", "Redis no está disponible", 503) from None
    return {
        "status": "ok",
        "llm_provider": get_settings().llm_provider,
        "embedding_provider": get_settings().embedding_provider,
    }


for router in (documents.router, batches.router, proposals.router):
    app.include_router(router)
