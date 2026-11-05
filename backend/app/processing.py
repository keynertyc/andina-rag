"""Application work, shared by Celery and integration tests. No queue orchestration here."""

import logging
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from sqlalchemy import select, text, update
from sqlalchemy.orm import Session

from app.db import get_engine
from app.embeddings import get_embedder
from app.errors import AppError, TransientError
from app.ingestion import chunk_sections, extract_sections
from app.llm import generate_validated, get_llm
from app.models import (
    Batch,
    BatchItem,
    Chunk,
    Document,
    DocumentVersion,
    Proposal,
    ProposalCitation,
    new_id,
)
from app.retrieval import retrieve
from app.schemas import Product
from app.telemetry import tracer

logger = logging.getLogger(__name__)


@contextmanager
def entity_session(entity_id: str) -> Iterator[Session]:
    # A dedicated connection owns this session-level lock across short transactions.
    # PostgreSQL releases it on connection/worker death; Redis is not a second lock store.
    lock_key = int(entity_id.replace("-", "")[:16], 16) - (1 << 63)
    with get_engine().connect() as connection:
        acquired = connection.scalar(text("SELECT pg_try_advisory_lock(:key)"), {"key": lock_key})
        connection.commit()
        if not acquired:
            raise TransientError("ITEM_BUSY")
        try:
            with Session(bind=connection, expire_on_commit=False) as session:
                yield session
        finally:
            if not connection.invalidated:
                connection.rollback()
                connection.execute(text("SELECT pg_advisory_unlock(:key)"), {"key": lock_key})
                connection.commit()


def ingest_version(version_id: str) -> None:
    with entity_session(version_id) as session:
        version = session.get(DocumentVersion, version_id)
        if not version or version.status == "ready":
            return
        if version.attempts >= 4:
            raise AppError("ATTEMPT_LIMIT", "Se agotaron los intentos; reenvía el documento")
        version.status = "indexing"
        version.error = None
        version.attempts += 1
        session.commit()
        embedder = get_embedder()
        if embedder.model_id != version.embedding_model:
            raise AppError("MODEL_CONFIGURATION_CHANGED", "Restaura la configuración del modelo")
        with tracer.start_as_current_span("document.extract"):
            sections = extract_sections(version.filename, Path(version.source_path).read_bytes())
        with tracer.start_as_current_span("document.chunk") as span:
            chunks = chunk_sections(
                sections,
                embedder.tokenizer,
                version.configuration["chunk_tokens"],
                version.configuration["chunk_overlap"],
            )
            span.set_attribute("document.chunks", len(chunks))
        vectors = embedder.passages([chunk.text for chunk in chunks])
        session.rollback()  # No database transaction is held during extraction/model work.
        session.execute(
            select(Document).where(Document.id == version.document_id).with_for_update()
        )
        session.add_all(
            [
                Chunk(
                    version_id=version_id,
                    position=index,
                    text=chunk.text,
                    page=chunk.page,
                    heading=chunk.heading,
                    embedding=vector,
                )
                for index, (chunk, vector) in enumerate(zip(chunks, vectors, strict=True))
            ]
        )
        current = session.scalar(
            select(DocumentVersion).where(
                DocumentVersion.document_id == version.document_id,
                DocumentVersion.is_active.is_(True),
            )
        )
        # A slow older upload must not replace a newer successfully indexed version.
        if current is None or current.number < version.number:
            session.execute(
                update(DocumentVersion)
                .where(
                    DocumentVersion.document_id == version.document_id,
                    DocumentVersion.is_active.is_(True),
                )
                .values(is_active=False)
            )
            session.flush()
            version.is_active = True
        version.status = "ready"
        version.error = None
        session.commit()


def process_item(item_id: str) -> None:
    with entity_session(item_id) as session:
        item = session.get(BatchItem, item_id)
        if not item or item.status in {"succeeded", "blocked", "failed"}:
            return
        if item.attempts >= 4:
            raise AppError("ATTEMPT_LIMIT", "Se agotaron los intentos; reintenta el producto")
        item.status = "running"
        item.attempts += 1
        item.error = None
        session.commit()
        batch = session.get(Batch, item.batch_id)
        assert batch is not None
        span = tracer.start_span(
            "product.enrich",
            attributes={
                "batch.id": batch.id,
                "product.id": item.product_id,
                "task.attempt": item.attempts,
            },
        )
        from opentelemetry import trace

        with trace.use_span(span, end_on_exit=True):
            from app.config import get_settings

            settings = get_settings()
            if (
                batch.configuration["llm_provider"] != settings.llm_provider
                or batch.configuration["llm_model"] != settings.gemini_model
            ):
                raise AppError("MODEL_CONFIGURATION_CHANGED", "Restaura la configuración del lote")
            product = Product.model_validate(item.original)
            if batch.configuration["embedding_model"] != get_embedder().model_id:
                raise AppError("MODEL_CONFIGURATION_CHANGED", "Restaura el modelo de embeddings")
            context = retrieve(
                session,
                product,
                batch.version_ids,
                get_embedder(),
                batch.configuration["threshold"],
                batch.configuration["top_k"],
            )
            if not context:
                raise AppError("INSUFFICIENT_EVIDENCE", "No se encontró evidencia suficiente")
            item.context_version_ids = sorted({chunk["version_id"] for chunk in context})
            session.commit()
            result = generate_validated(get_llm(), product, context)
            proposal = Proposal(
                id=new_id(),
                item_id=item.id,
                generated=result.model_dump(),
                content=result.model_dump(),
            )
            session.add(proposal)
            session.flush()
            session.add_all(
                [
                    ProposalCitation(proposal_id=proposal.id, chunk_id=chunk_id)
                    for chunk_id in result.citations
                ]
            )
            item.status = "succeeded"
            item.error = None
            session.commit()
            logger.info(
                "product_enriched", extra={"batch_id": batch.id, "product_id": item.product_id}
            )


def record_task_error(kind: str, entity_id: str, status: str, error: dict[str, Any]) -> None:
    with Session(get_engine()) as session:
        entity: BatchItem | DocumentVersion | None = (
            session.get(BatchItem, entity_id)
            if kind == "item"
            else session.get(DocumentVersion, entity_id)
        )
        if entity is not None and entity.status not in {"succeeded", "ready"}:
            entity.status = status
            entity.error = error
            session.commit()
