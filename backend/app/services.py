from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import get_settings
from app.embeddings import configured_model_id
from app.errors import AppError
from app.imports import request_fingerprint
from app.models import (
    Batch,
    BatchItem,
    DocumentVersion,
)
from app.schemas import Product


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
