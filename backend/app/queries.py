"""Read models loaded in bounded queries, including paginated list views."""

from collections import Counter
from collections.abc import Sequence
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import (
    Batch,
    BatchItem,
    Chunk,
    Document,
    DocumentVersion,
    Proposal,
    ProposalCitation,
)
from app.reviews import allowed_actions, proposal_is_stale


def batch_view(
    session: Session, batch: Batch, counts: Counter[str] | None = None
) -> dict[str, Any]:
    counts = (
        counts
        if counts is not None
        else Counter(
            {
                status: count
                for status, count in session.execute(
                    select(BatchItem.status, func.count())
                    .where(BatchItem.batch_id == batch.id)
                    .group_by(BatchItem.status)
                )
            }
        )
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


def proposal_view(
    session: Session,
    proposal: Proposal,
    detail: bool = False,
    *,
    item: BatchItem | None = None,
    stale: bool | None = None,
) -> dict[str, Any]:
    item = item if item is not None else session.get(BatchItem, proposal.item_id)
    assert item is not None
    stale = proposal_is_stale(session, item) if stale is None else stale
    result = {
        "id": proposal.id,
        "item_id": item.id,
        "batch_id": item.batch_id,
        "product_id": item.product_id,
        "original": item.original,
        "content": proposal.content,
        "status": proposal.status,
        "revision": proposal.revision,
        "is_stale": stale,
        "allowed_actions": allowed_actions(proposal.status, stale),
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


def batch_list_views(session: Session, batches: Sequence[Batch]) -> list[dict[str, Any]]:
    counts: dict[str, Counter[str]] = {batch.id: Counter() for batch in batches}
    if batches:
        for batch_id, status, count in session.execute(
            select(BatchItem.batch_id, BatchItem.status, func.count())
            .where(BatchItem.batch_id.in_(counts))
            .group_by(BatchItem.batch_id, BatchItem.status)
        ):
            counts[batch_id][status] = count
    return [batch_view(session, batch, counts[batch.id]) for batch in batches]


def proposal_list_views(session: Session, rows: Sequence[Any]) -> list[dict[str, Any]]:
    version_ids = {version_id for _, item in rows for version_id in item.context_version_ids}
    active = (
        set(
            session.scalars(
                select(DocumentVersion.id).where(
                    DocumentVersion.id.in_(version_ids), DocumentVersion.is_active.is_(True)
                )
            )
        )
        if version_ids
        else set()
    )
    return [
        proposal_view(
            session, proposal, item=item, stale=not set(item.context_version_ids).issubset(active)
        )
        for proposal, item in rows
    ]
