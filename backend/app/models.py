from datetime import datetime
from typing import Any
from uuid import uuid4

from pgvector.sqlalchemy import Vector
from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy import text as sql_text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


def new_id() -> str:
    return str(uuid4())


class Record:
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=sql_text("now()")
    )


class Document(Record, Base):
    __tablename__ = "documents"
    title: Mapped[str] = mapped_column(String(200))
    brand: Mapped[str | None] = mapped_column(String(100), index=True)
    category: Mapped[str | None] = mapped_column(String(100), index=True)


class DocumentVersion(Record, Base):
    __tablename__ = "document_versions"
    __table_args__ = (
        UniqueConstraint("document_id", "number"),
        UniqueConstraint("document_id", "checksum"),
        Index(
            "uq_active_document_version",
            "document_id",
            unique=True,
            postgresql_where=sql_text("is_active"),
        ),
    )
    document_id: Mapped[str] = mapped_column(ForeignKey("documents.id"), index=True)
    number: Mapped[int] = mapped_column(Integer)
    checksum: Mapped[str] = mapped_column(String(64))
    filename: Mapped[str] = mapped_column(String(255))
    source_path: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="pending")
    is_active: Mapped[bool] = mapped_column(Boolean, default=False)
    error: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    embedding_model: Mapped[str] = mapped_column(String(200))
    configuration: Mapped[dict[str, Any]] = mapped_column(JSONB)
    attempts: Mapped[int] = mapped_column(Integer, default=0)


class Chunk(Record, Base):
    __tablename__ = "chunks"
    __table_args__ = (UniqueConstraint("version_id", "position"),)
    version_id: Mapped[str] = mapped_column(ForeignKey("document_versions.id"), index=True)
    position: Mapped[int] = mapped_column(Integer)
    text: Mapped[str] = mapped_column(Text)
    page: Mapped[int | None] = mapped_column(Integer)
    heading: Mapped[str | None] = mapped_column(String(300))
    embedding: Mapped[Any] = mapped_column(Vector(384))


class Batch(Record, Base):
    __tablename__ = "batches"
    idempotency_key: Mapped[str] = mapped_column(String(128), unique=True)
    request_hash: Mapped[str] = mapped_column(String(64))
    filename: Mapped[str] = mapped_column(String(255))
    version_ids: Mapped[list[str]] = mapped_column(JSONB)
    configuration: Mapped[dict[str, Any]] = mapped_column(JSONB)
    dispatch_error: Mapped[dict[str, Any] | None] = mapped_column(JSONB)


class BatchItem(Record, Base):
    __tablename__ = "batch_items"
    __table_args__ = (UniqueConstraint("batch_id", "product_id"),)
    batch_id: Mapped[str] = mapped_column(ForeignKey("batches.id"), index=True)
    product_id: Mapped[str] = mapped_column(String(100))
    original: Mapped[dict[str, Any]] = mapped_column(JSONB)
    status: Mapped[str] = mapped_column(String(20), default="pending", index=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    context_version_ids: Mapped[list[str]] = mapped_column(JSONB, default=list)


class Proposal(Record, Base):
    __tablename__ = "proposals"
    item_id: Mapped[str] = mapped_column(ForeignKey("batch_items.id"), unique=True)
    generated: Mapped[dict[str, Any]] = mapped_column(JSONB)
    content: Mapped[dict[str, Any]] = mapped_column(JSONB)
    status: Mapped[str] = mapped_column(String(20), default="pending_review", index=True)
    revision: Mapped[int] = mapped_column(Integer, default=1)


class ProposalCitation(Base):
    __tablename__ = "proposal_citations"
    proposal_id: Mapped[str] = mapped_column(ForeignKey("proposals.id"), primary_key=True)
    chunk_id: Mapped[str] = mapped_column(ForeignKey("chunks.id"), primary_key=True, index=True)
