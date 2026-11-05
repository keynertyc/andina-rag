"""Small shared HTTP dependencies and upload limits."""

from collections.abc import Sequence
from pathlib import Path
from typing import Annotated, Any
from uuid import UUID

from fastapi import Depends, Header, Response, UploadFile
from sqlalchemy.orm import Session

from app.db import get_session
from app.errors import AppError

SessionDep = Annotated[Session, Depends(get_session)]
IdempotencyKey = Annotated[str, Header(alias="Idempotency-Key", min_length=1, max_length=128)]


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


def page_header(response: Response, rows: Sequence[Any], limit: int) -> None:
    response.headers["X-Has-More"] = str(len(rows) > limit).lower()
