"""Version creation, duplicate recovery and source file storage."""

import hashlib

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.embeddings import configured_model_id
from app.errors import AppError, TransientError
from app.ingestion import validate_source
from app.models import Document, DocumentVersion, new_id
from app.processing import entity_session


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
            try:
                with entity_session(existing.id) as locked:
                    retry_version = locked.get(DocumentVersion, existing.id)
                    assert retry_version is not None
                    if retry_version.status == "error":
                        retry_version.status, retry_version.error, retry_version.attempts = (
                            "pending",
                            None,
                            0,
                        )
                        locked.commit()
            except TransientError:
                raise AppError("DOCUMENT_BUSY", "La versión se está procesando", 409) from None
            session.refresh(existing)
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
