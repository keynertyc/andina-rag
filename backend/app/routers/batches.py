from typing import Annotated, Any, Literal
from uuid import UUID

from fastapi import APIRouter, File, Query, Response, UploadFile
from sqlalchemy import select

from app.dispatch import publish_batch
from app.http import IdempotencyKey, SessionDep, page_header, read_file, required
from app.imports import parse_products
from app.models import Batch, BatchItem
from app.queries import (
    batch_list_views,
    batch_view,
)
from app.schemas import (
    BatchItemView,
    BatchView,
)
from app.services import create_batch

router = APIRouter(prefix="/api/v1")


@router.post("/batches", status_code=202, response_model=BatchView)
def upload_batch(
    session: SessionDep, file: Annotated[UploadFile, File()], idempotency_key: IdempotencyKey
) -> dict[str, Any]:
    filename, content = read_file(file, 5 * 1024 * 1024)
    batch = create_batch(session, parse_products(filename, content), filename, idempotency_key)
    publish_batch(session, batch)
    return batch_view(session, batch)


@router.get("/batches", response_model=list[BatchView])
def list_batches(
    session: SessionDep,
    response: Response,
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
) -> list[dict[str, Any]]:
    rows = list(
        session.scalars(
            select(Batch)
            .order_by(Batch.created_at.desc(), Batch.id)
            .limit(limit + 1)
            .offset(offset)
        )
    )
    page_header(response, rows, limit)
    return batch_list_views(session, rows[:limit])


@router.get("/batches/{batch_id}", response_model=BatchView)
def get_batch(batch_id: UUID, session: SessionDep) -> dict[str, Any]:
    return batch_view(session, required(session, Batch, batch_id))


@router.get("/batches/{batch_id}/items", response_model=list[BatchItemView])
def list_batch_items(
    batch_id: UUID,
    session: SessionDep,
    response: Response,
    limit: int = Query(50, ge=1, le=1000),
    offset: int = Query(0, ge=0),
) -> list[dict[str, Any]]:
    required(session, Batch, batch_id)
    rows = list(
        session.scalars(
            select(BatchItem)
            .where(BatchItem.batch_id == str(batch_id))
            .order_by(BatchItem.product_id, BatchItem.id)
            .limit(limit + 1)
            .offset(offset)
        )
    )
    page_header(response, rows, limit)
    return [
        {
            "id": i.id,
            "product_id": i.product_id,
            "original": i.original,
            "status": i.status,
            "attempts": i.attempts,
            "error": i.error,
        }
        for i in rows[:limit]
    ]


@router.post("/batches/{batch_id}/retry", status_code=202, response_model=BatchView)
def retry_batch(
    batch_id: UUID, session: SessionDep, mode: Literal["failed", "unfinished"] = "failed"
) -> dict[str, Any]:
    batch = required(session, Batch, batch_id)
    publish_batch(session, batch, mode=mode)
    return batch_view(session, batch)
