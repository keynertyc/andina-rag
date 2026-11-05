from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, File, Form, Query, Response, UploadFile
from sqlalchemy import select

from app.dispatch import publish_document
from app.documents import store_version
from app.errors import AppError
from app.http import SessionDep, page_header, read_file, required
from app.ingestion import validate_source
from app.models import Document, DocumentVersion
from app.schemas import DocumentUploadResult, DocumentView

router = APIRouter(prefix="/api/v1")


@router.post("/documents", status_code=202, response_model=DocumentUploadResult)
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


@router.post(
    "/documents/{document_id}/versions", status_code=202, response_model=DocumentUploadResult
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


@router.get("/documents", response_model=list[DocumentView])
def list_documents(
    session: SessionDep,
    response: Response,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    latest_only: bool = False,
    document_id: UUID | None = None,
) -> list[dict[str, Any]]:
    statement = select(Document, DocumentVersion).join(DocumentVersion)
    if document_id:
        statement = statement.where(Document.id == str(document_id))
    if latest_only:
        statement = statement.distinct(Document.id)
    statement = (
        statement.order_by(Document.id, DocumentVersion.number.desc())
        if latest_only
        else statement.order_by(
            Document.created_at.desc(), Document.id, DocumentVersion.number.desc()
        )
    )
    page = session.execute(statement.limit(limit + 1).offset(offset)).all()
    page_header(response, page, limit)
    return [
        {
            "id": d.id,
            "title": d.title,
            "brand": d.brand,
            "category": d.category,
            "version_id": v.id,
            "version": v.number,
            "status": v.status,
            "is_active": v.is_active,
            "error": v.error,
            "filename": v.filename,
        }
        for d, v in page[:limit]
    ]
