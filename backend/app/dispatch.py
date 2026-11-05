"""Queue publication and deliberate recovery. PostgreSQL remains the source of state."""

from typing import Literal

from kombu.exceptions import OperationalError as BrokerError
from redis.exceptions import RedisError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.errors import AppError, TransientError
from app.models import Batch, BatchItem, DocumentVersion
from app.processing import entity_session
from app.tasks import enrich_task, ingest_task


def publish_document(session: Session, version: DocumentVersion) -> None:
    try:
        with entity_session(version.id) as locked:
            current = locked.get(DocumentVersion, version.id)
            assert current is not None
            if current.status == "ready":
                return
            try:
                ingest_task.apply_async(args=[version.id], headers={"source": "api"}, retry=False)
            except (BrokerError, RedisError, OSError):
                current.status = "error"
                current.error = {
                    "code": "BROKER_UNAVAILABLE",
                    "message": "Reenvía la misma versión",
                }
                locked.commit()
                raise AppError(
                    "BROKER_UNAVAILABLE",
                    "Guía guardada; Redis no está disponible",
                    503,
                    document_id=version.document_id,
                    version_id=version.id,
                ) from None
    except TransientError as exc:
        if exc.code != "ITEM_BUSY":
            raise
    session.refresh(version)


def publish_batch(
    session: Session, batch: Batch, mode: Literal["dispatch", "failed", "unfinished"] = "dispatch"
) -> None:
    item_ids = list(
        session.scalars(
            select(BatchItem.id).where(BatchItem.batch_id == batch.id).order_by(BatchItem.id)
        )
    )
    session.commit()
    try:
        for item_id in item_ids:
            try:
                with entity_session(item_id) as locked:
                    item = locked.get(BatchItem, item_id)
                    assert item is not None
                    if mode == "failed":
                        if item.status != "failed":
                            continue
                        item.status, item.error, item.attempts = "pending", None, 0
                        locked.commit()
                    elif item.status not in {"pending", "running"}:
                        continue
                    # A running item can only be recovered if no worker owns its lock.
                    enrich_task.apply_async(args=[item.id], headers={"source": "api"}, retry=False)
            except TransientError as exc:
                if exc.code != "ITEM_BUSY":
                    raise
        # Retrying failed items does not recover other pending, unpublished work.
        if mode != "failed":
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
