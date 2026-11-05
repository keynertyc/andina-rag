import hashlib
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated, Any
from uuid import UUID

from fastapi import Depends, FastAPI, File, Form, Header, Query, Request, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from kombu.exceptions import OperationalError as BrokerError
from opentelemetry import trace
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.sdk.trace import TracerProvider
from pydantic import ValidationError
from redis import Redis
from redis.exceptions import RedisError
from sqlalchemy import func, select, text
from sqlalchemy.exc import InterfaceError, OperationalError
from sqlalchemy.orm import Session
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.config import get_settings
from app.db import get_session
from app.embeddings import configured_model_id
from app.errors import AppError
from app.imports import parse_products
from app.ingestion import validate_source
from app.models import Batch, BatchItem, Document, DocumentVersion, Proposal, new_id
from app.schemas import (
    BatchItemView,
    BatchView,
    DocumentUploadResult,
    DocumentView,
    GeneratedProposal,
    Product,
    ProposalDetailView,
    ProposalUpdate,
    ProposalView,
)
from app.services import batch_view, create_batch, proposal_is_stale, proposal_view
from app.tasks import enrich_task, ingest_task
from app.telemetry import configure_telemetry

logger = logging.getLogger(__name__)
SessionDep = Annotated[Session, Depends(get_session)]
IdempotencyKey = Annotated[str, Header(alias="Idempotency-Key", min_length=1, max_length=128)]


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


def read_file(upload: UploadFile, limit: int) -> tuple[str, bytes]:
    content = upload.file.read(limit + 1)
    if len(content) > limit:
        raise AppError("FILE_TOO_LARGE", "El archivo supera el tamaño máximo", 413)
    filename = Path(upload.filename or "upload").name[:255]
    return filename, content


def required(session: Session, model: Any, identifier: UUID | str) -> Any:
    instance = session.get(model, str(identifier))
    if instance is None:
        raise AppError("NOT_FOUND", "No se encontró el recurso", 404)
    return instance


def publish_document(session: Session, version: DocumentVersion) -> None:
    try:
        ingest_task.apply_async(args=[version.id], headers={"source": "api"}, retry=False)
    except (BrokerError, RedisError, OSError):
        version.status = "error"
        version.error = {"code": "BROKER_UNAVAILABLE", "message": "Reenvía la misma versión"}
        session.commit()
        raise AppError(
            "BROKER_UNAVAILABLE",
            "Guía guardada; Redis no está disponible",
            503,
            document_id=version.document_id,
            version_id=version.id,
        ) from None


def publish_batch(session: Session, batch: Batch, reset_failed: bool = False) -> None:
    items = list(session.scalars(select(BatchItem).where(BatchItem.batch_id == batch.id)))
    if reset_failed:
        for item in items:
            if item.status == "failed":
                item.status, item.error, item.attempts = "pending", None, 0
        session.commit()
    try:
        for item in items:
            if item.status in {"pending", "running"}:
                enrich_task.apply_async(args=[item.id], headers={"source": "api"}, retry=False)
        batch.dispatch_error = None
        session.commit()
    except (BrokerError, RedisError, OSError):
        batch.dispatch_error = {
            "code": "BROKER_UNAVAILABLE",
            "message": "Reenvía el lote pendiente",
        }
        session.commit()
        raise AppError(
            "BROKER_UNAVAILABLE", "Lote guardado; no se completó el envío", 503, batch_id=batch.id
        ) from None


def store_version(
    session: Session,
    document: Document,
    filename: str,
    content: bytes,
) -> DocumentVersion:
    validate_source(filename, content)
    checksum = hashlib.sha256(content).hexdigest()
    # Serialize new version numbers and duplicate content uploads for the same logical guide.
    session.execute(select(Document).where(Document.id == document.id).with_for_update())
    existing = session.scalar(
        select(DocumentVersion).where(
            DocumentVersion.document_id == document.id, DocumentVersion.checksum == checksum
        )
    )
    if existing:
        if existing.status == "error":
            existing.status, existing.error, existing.attempts = "pending", None, 0
        session.commit()
        return existing
    number = (
        session.scalar(
            select(func.max(DocumentVersion.number)).where(
                DocumentVersion.document_id == document.id
            )
        )
        or 0
    ) + 1
    identifier = new_id()
    path = get_settings().upload_dir / identifier
    path.write_bytes(content)
    settings = get_settings()
    version = DocumentVersion(
        id=identifier,
        document_id=document.id,
        number=number,
        checksum=checksum,
        filename=filename,
        source_path=str(path.resolve()),
        embedding_model=configured_model_id(),
        configuration={
            "chunk_tokens": settings.chunk_tokens,
            "chunk_overlap": settings.chunk_overlap,
        },
    )
    try:
        session.add(version)
        session.commit()
    except Exception:
        path.unlink(missing_ok=True)
        raise
    return version


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


@app.post("/api/v1/documents", status_code=202, response_model=DocumentUploadResult)
def upload_document(
    session: SessionDep,
    file: Annotated[UploadFile, File()],
    title: Annotated[str, Form(min_length=1, max_length=200)],
    brand: Annotated[str, Form(max_length=100)] = "",
    category: Annotated[str, Form(max_length=100)] = "",
) -> dict[str, Any]:
    filename, content = read_file(file, 10 * 1024 * 1024)
    validate_source(filename, content)
    document = Document(
        title=title.strip(),
        brand=brand.strip().casefold() or None,
        category=category.strip().casefold() or None,
    )
    if not document.title:
        raise AppError("INVALID_TITLE", "Indica un título para la guía")
    session.add(document)
    session.flush()
    version = store_version(session, document, filename, content)
    publish_document(session, version)
    return {"document_id": document.id, "version_id": version.id, "status": version.status}


@app.post(
    "/api/v1/documents/{document_id}/versions", status_code=202, response_model=DocumentUploadResult
)
def upload_version(
    document_id: UUID, session: SessionDep, file: Annotated[UploadFile, File()]
) -> dict[str, Any]:
    document = required(session, Document, document_id)
    filename, content = read_file(file, 10 * 1024 * 1024)
    version = store_version(session, document, filename, content)
    if version.status != "ready":
        publish_document(session, version)
    return {"document_id": document.id, "version_id": version.id, "status": version.status}


@app.get("/api/v1/documents", response_model=list[DocumentView])
def list_documents(
    session: SessionDep, limit: int = Query(100, ge=1, le=200), offset: int = Query(0, ge=0)
) -> list[dict[str, Any]]:
    rows = session.execute(
        select(Document, DocumentVersion)
        .join(DocumentVersion)
        .order_by(Document.created_at.desc(), DocumentVersion.number.desc())
        .limit(limit)
        .offset(offset)
    )
    return [
        {
            "id": document.id,
            "title": document.title,
            "brand": document.brand,
            "category": document.category,
            "version_id": version.id,
            "version": version.number,
            "status": version.status,
            "is_active": version.is_active,
            "error": version.error,
            "filename": version.filename,
        }
        for document, version in rows
    ]


@app.post("/api/v1/batches", status_code=202, response_model=BatchView)
def upload_batch(
    session: SessionDep, file: Annotated[UploadFile, File()], idempotency_key: IdempotencyKey
) -> dict[str, Any]:
    filename, content = read_file(file, 5 * 1024 * 1024)
    batch = create_batch(session, parse_products(filename, content), filename, idempotency_key)
    publish_batch(session, batch)
    return batch_view(session, batch)


@app.get("/api/v1/batches", response_model=list[BatchView])
def list_batches(
    session: SessionDep, limit: int = Query(50, ge=1, le=100), offset: int = Query(0, ge=0)
) -> list[dict[str, Any]]:
    return [
        batch_view(session, batch)
        for batch in session.scalars(
            select(Batch).order_by(Batch.created_at.desc()).limit(limit).offset(offset)
        )
    ]


@app.get("/api/v1/batches/{batch_id}", response_model=BatchView)
def get_batch(batch_id: UUID, session: SessionDep) -> dict[str, Any]:
    return batch_view(session, required(session, Batch, batch_id))


@app.get("/api/v1/batches/{batch_id}/items", response_model=list[BatchItemView])
def list_batch_items(
    batch_id: UUID,
    session: SessionDep,
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
) -> list[dict[str, Any]]:
    required(session, Batch, batch_id)
    return [
        {
            "id": item.id,
            "product_id": item.product_id,
            "original": item.original,
            "status": item.status,
            "attempts": item.attempts,
            "error": item.error,
        }
        for item in session.scalars(
            select(BatchItem)
            .where(BatchItem.batch_id == str(batch_id))
            .order_by(BatchItem.product_id)
            .limit(limit)
            .offset(offset)
        )
    ]


@app.post("/api/v1/batches/{batch_id}/retry", status_code=202, response_model=BatchView)
def retry_batch(batch_id: UUID, session: SessionDep) -> dict[str, Any]:
    batch = required(session, Batch, batch_id)
    publish_batch(session, batch, reset_failed=True)
    return batch_view(session, batch)


@app.get("/api/v1/proposals", response_model=list[ProposalView])
def list_proposals(
    session: SessionDep,
    status: str | None = None,
    batch_id: UUID | None = None,
    limit: int = Query(100, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> list[dict[str, Any]]:
    statement = select(Proposal).join(BatchItem)
    if status:
        if status not in {"pending_review", "approved", "rejected"}:
            raise AppError("INVALID_STATUS", "Estado de propuesta desconocido")
        statement = statement.where(Proposal.status == status)
    if batch_id:
        statement = statement.where(BatchItem.batch_id == str(batch_id))
    return [
        proposal_view(session, proposal)
        for proposal in session.scalars(
            statement.order_by(Proposal.created_at.desc()).limit(limit).offset(offset)
        )
    ]


@app.get("/api/v1/proposals/{proposal_id}", response_model=ProposalDetailView)
def get_proposal(proposal_id: UUID, session: SessionDep) -> dict[str, Any]:
    return proposal_view(session, required(session, Proposal, proposal_id), detail=True)


@app.patch("/api/v1/proposals/{proposal_id}", response_model=ProposalDetailView)
def update_proposal(proposal_id: UUID, data: ProposalUpdate, session: SessionDep) -> dict[str, Any]:
    proposal = session.scalar(
        select(Proposal).where(Proposal.id == str(proposal_id)).with_for_update()
    )
    if not proposal:
        raise AppError("NOT_FOUND", "No se encontró la propuesta", 404)
    if proposal.revision != data.revision:
        raise AppError("REVISION_CONFLICT", "La propuesta cambió; recarga antes de guardar", 409)
    item = required(session, BatchItem, proposal.item_id)
    # Activation also locks the document row; approval and activation are serialized.
    session.execute(
        select(Document.id)
        .join(DocumentVersion)
        .where(DocumentVersion.id.in_(item.context_version_ids))
        .order_by(Document.id)
        .with_for_update(of=Document)
    ).all()
    if data.status == "approved" and proposal_is_stale(session, item):
        raise AppError("STALE_PROPOSAL", "Regenera la propuesta con las guías vigentes", 409)
    changes = data.model_dump(exclude_none=True, exclude={"revision", "status"})
    try:
        content = GeneratedProposal.model_validate({**proposal.content, **changes})
    except ValidationError as exc:
        raise AppError(
            "INVALID_PROPOSAL", "Revisa las etiquetas y los campos de la propuesta"
        ) from exc
    proposal.content = content.model_dump()
    proposal.status = data.status or ("pending_review" if changes else proposal.status)
    proposal.revision += 1
    session.commit()
    return proposal_view(session, proposal, detail=True)


@app.post("/api/v1/proposals/{proposal_id}/regenerate", status_code=202, response_model=BatchView)
def regenerate_proposal(
    proposal_id: UUID, session: SessionDep, idempotency_key: IdempotencyKey
) -> dict[str, Any]:
    proposal = required(session, Proposal, proposal_id)
    item = required(session, BatchItem, proposal.item_id)
    batch = create_batch(
        session,
        [Product.model_validate(item.original)],
        f"Regeneración de {item.product_id}",
        idempotency_key,
    )
    publish_batch(session, batch)
    return batch_view(session, batch)
