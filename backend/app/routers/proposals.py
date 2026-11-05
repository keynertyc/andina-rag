from typing import Any
from uuid import UUID

from fastapi import APIRouter, Query, Response
from sqlalchemy import select

from app.dispatch import publish_batch
from app.errors import AppError
from app.http import IdempotencyKey, SessionDep, page_header, required
from app.models import BatchItem, Proposal
from app.queries import batch_view, proposal_list_views, proposal_view
from app.reviews import allowed_actions, proposal_is_stale, review_proposal
from app.schemas import BatchView, Product, ProposalDetailView, ProposalUpdate, ProposalView
from app.services import create_batch

router = APIRouter(prefix="/api/v1")


@router.get("/proposals", response_model=list[ProposalView])
def list_proposals(
    session: SessionDep,
    response: Response,
    status: str | None = None,
    batch_id: UUID | None = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> list[dict[str, Any]]:
    statement = select(Proposal, BatchItem).join(BatchItem)
    if status:
        if status not in {"pending_review", "approved", "rejected"}:
            raise AppError("INVALID_STATUS", "Estado de propuesta desconocido")
        statement = statement.where(Proposal.status == status)
    if batch_id:
        statement = statement.where(BatchItem.batch_id == str(batch_id))
    rows = session.execute(
        statement.order_by(Proposal.created_at.desc(), Proposal.id).limit(limit + 1).offset(offset)
    ).all()
    page_header(response, rows, limit)
    return proposal_list_views(session, rows[:limit])


@router.get("/proposals/{proposal_id}", response_model=ProposalDetailView)
def get_proposal(proposal_id: UUID, session: SessionDep) -> dict[str, Any]:
    return proposal_view(session, required(session, Proposal, proposal_id), detail=True)


@router.patch("/proposals/{proposal_id}", response_model=ProposalDetailView)
def update_proposal(proposal_id: UUID, data: ProposalUpdate, session: SessionDep) -> dict[str, Any]:
    proposal = review_proposal(session, str(proposal_id), data)
    return proposal_view(session, proposal, detail=True)


@router.post("/proposals/{proposal_id}/regenerate", status_code=202, response_model=BatchView)
def regenerate_proposal(
    proposal_id: UUID, session: SessionDep, idempotency_key: IdempotencyKey
) -> dict[str, Any]:
    proposal = required(session, Proposal, proposal_id)
    item = required(session, BatchItem, proposal.item_id)
    if "regenerate" not in allowed_actions(proposal.status, proposal_is_stale(session, item)):
        raise AppError("REGENERATION_NOT_REQUIRED", "La propuesta ya usa guías vigentes", 409)
    batch = create_batch(
        session,
        [Product.model_validate(item.original)],
        f"Regeneración de {item.product_id}",
        idempotency_key,
    )
    publish_batch(session, batch)
    return batch_view(session, batch)
