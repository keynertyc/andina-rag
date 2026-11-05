from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.embeddings import Embedder
from app.models import Chunk, Document, DocumentVersion
from app.schemas import Product
from app.telemetry import tracer


def retrieve(
    session: Session,
    product: Product,
    version_ids: list[str],
    embedder: Embedder,
    threshold: float | None = None,
    top_k: int | None = None,
) -> list[dict[str, Any]]:
    settings = get_settings()
    with tracer.start_as_current_span("rag.retrieve") as span:
        # Scope is enforced by metadata. Repeating brand/category in the query can make
        # a generic brand heading look relevant to an unrelated product.
        query = " ".join([product.title, product.description])
        vector = embedder.query(query)
        distance = Chunk.embedding.cosine_distance(vector)
        statement = (
            select(Chunk, DocumentVersion, Document, (1 - distance).label("similarity"))
            .join(DocumentVersion, Chunk.version_id == DocumentVersion.id)
            .join(Document, DocumentVersion.document_id == Document.id)
            .where(
                DocumentVersion.id.in_(version_ids),
                DocumentVersion.embedding_model == embedder.model_id,
                or_(Document.brand.is_(None), Document.brand == product.brand.casefold()),
                or_(Document.category.is_(None), Document.category == product.category.casefold()),
                distance
                <= 1 - (threshold if threshold is not None else settings.similarity_threshold),
            )
            .order_by(distance, Chunk.id)
            .limit(top_k or settings.top_k)
        )
        results = [
            {
                "id": chunk.id,
                "text": chunk.text,
                "document_id": document.id,
                "document_title": document.title,
                "version_id": version.id,
                "version": version.number,
                "page": chunk.page,
                "heading": chunk.heading,
                "similarity": float(similarity),
            }
            for chunk, version, document, similarity in session.execute(statement)
        ]
        span.set_attribute("rag.retrieved_chunks", len(results))
        span.set_attribute("rag.category", product.category)
        span.set_attribute("rag.brand", product.brand)
        return results
