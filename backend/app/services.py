from collections import Counter
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import get_settings
from app.embeddings import configured_model_id
from app.errors import AppError
from app.imports import request_fingerprint
from app.models import (
    Batch,
    BatchItem,
    Chunk,
    Document,
    DocumentVersion,
    Proposal,
    ProposalCitation,
)
from app.schemas import Product


def batch_view(session: Session, batch: Batch) -> dict[str, Any]:
    counts: Counter[str] = Counter(
        {
            status: count
            for status, count in session.execute(
                select(BatchItem.status, func.count())
                .where(BatchItem.batch_id == batch.id)
                .group_by(BatchItem.status)
            )
        }
    )
    total = sum(counts.values())
    finished = counts["succeeded"] + counts["blocked"] + counts["failed"]
    terminal = finished == total
    if batch.dispatch_error or (terminal and (counts["blocked"] or counts["failed"])):
        status = "with_errors"
    elif terminal:
        status = "completed"
    elif counts["running"] or finished:
        status = "running"
    else:
        status = "pending"
    return {
        "id": batch.id,
        "filename": batch.filename,
        "created_at": batch.created_at,
        "status": status,
        "total": total,
        "finished": finished,
        "terminal": terminal,
        "counts": dict(counts),
        "dispatch_error": batch.dispatch_error,
        "configuration": batch.configuration,
    }


def create_batch(
    session: Session,
    products: list[Product],
    filename: str,
    key: str,
) -> Batch:
    fingerprint = request_fingerprint(products)
    existing = session.scalar(select(Batch).where(Batch.idempotency_key == key))
    if existing:
        if existing.request_hash != fingerprint:
            raise AppError(
                "IDEMPOTENCY_CONFLICT", "La clave ya se utilizó con otros productos", 409
            )
        return existing
    settings = get_settings()
    versions = list(
        session.scalars(
            select(DocumentVersion.id).where(
                DocumentVersion.is_active.is_(True),
                DocumentVersion.embedding_model == configured_model_id(),
            )
        )
    )
    batch = Batch(
        idempotency_key=key,
        request_hash=fingerprint,
        filename=filename,
        version_ids=versions,
        configuration={
            "llm_provider": settings.llm_provider,
            "llm_model": settings.gemini_model,
            "embedding_model": configured_model_id(),
            "threshold": settings.similarity_threshold,
            "top_k": settings.top_k,
        },
    )
    try:
        session.add(batch)
        session.flush()
        session.add_all(
            [
                BatchItem(batch_id=batch.id, product_id=product.id, original=product.model_dump())
                for product in products
            ]
        )
        session.commit()
    except IntegrityError:
        session.rollback()
        existing = session.scalar(select(Batch).where(Batch.idempotency_key == key))
        if existing is None:
            raise
        if existing.request_hash != fingerprint:
            raise AppError(
                "IDEMPOTENCY_CONFLICT", "Clave utilizada con otros productos", 409
            ) from None
        return existing
    return batch


def proposal_is_stale(session: Session, item: BatchItem) -> bool:
    if not item.context_version_ids:
        return False
    active_count = session.scalar(
        select(func.count())
        .select_from(DocumentVersion)
        .where(
            DocumentVersion.id.in_(item.context_version_ids), DocumentVersion.is_active.is_(True)
        )
    )
    return active_count != len(item.context_version_ids)


def proposal_view(session: Session, proposal: Proposal, detail: bool = False) -> dict[str, Any]:
    item = session.get(BatchItem, proposal.item_id)
    assert item is not None
    result = {
        "id": proposal.id,
        "item_id": item.id,
        "batch_id": item.batch_id,
        "product_id": item.product_id,
        "original": item.original,
        "content": proposal.content,
        "status": proposal.status,
        "revision": proposal.revision,
        "is_stale": proposal_is_stale(session, item),
        "created_at": proposal.created_at,
    }
    if detail:
        result["generated"] = proposal.generated
        rows = session.execute(
            select(Chunk, DocumentVersion, Document)
            .join(ProposalCitation, ProposalCitation.chunk_id == Chunk.id)
            .join(DocumentVersion, DocumentVersion.id == Chunk.version_id)
            .join(Document, Document.id == DocumentVersion.document_id)
            .where(ProposalCitation.proposal_id == proposal.id)
            .order_by(Chunk.position)
        )
        result["citations"] = [
            {
                "id": chunk.id,
                "text": chunk.text,
                "document_title": document.title,
                "version": version.number,
                "page": chunk.page,
                "heading": chunk.heading,
            }
            for chunk, version, document in rows
        ]
    return result
