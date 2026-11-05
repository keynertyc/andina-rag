"""Review policy and atomic analyst decisions; independent of HTTP and Celery."""

from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.errors import AppError
from app.models import BatchItem, Document, DocumentVersion, Proposal
from app.schemas import GeneratedProposal, ProposalUpdate, ReviewAction


def allowed_actions(status: str, stale: bool) -> list[ReviewAction]:
    if stale:
        return ["reject", "regenerate"] if status == "pending_review" else ["regenerate"]
    return ["edit", "approve", "reject"] if status == "pending_review" else ["reopen"]


def proposal_is_stale(session: Session, item: BatchItem) -> bool:
    if not item.context_version_ids:
        return False
    count = session.scalar(
        select(func.count())
        .select_from(DocumentVersion)
        .where(
            DocumentVersion.id.in_(item.context_version_ids), DocumentVersion.is_active.is_(True)
        )
    )
    return count != len(item.context_version_ids)


def review_proposal(session: Session, proposal_id: str, data: ProposalUpdate) -> Proposal:
    proposal = session.scalar(select(Proposal).where(Proposal.id == proposal_id).with_for_update())
    if proposal is None:
        raise AppError("NOT_FOUND", "No se encontró la propuesta", 404)
    if proposal.revision != data.revision:
        raise AppError("REVISION_CONFLICT", "La propuesta cambió; compara antes de guardar", 409)
    item = session.get(BatchItem, proposal.item_id)
    assert item is not None
    # Version activation locks the same document rows, in the same order.
    session.execute(
        select(Document.id)
        .join(DocumentVersion)
        .where(DocumentVersion.id.in_(item.context_version_ids))
        .order_by(Document.id)
        .with_for_update(of=Document)
    ).all()
    stale = proposal_is_stale(session, item)
    changes = data.model_dump(exclude_none=True, exclude={"revision", "status"})
    try:
        content = GeneratedProposal.model_validate({**proposal.content, **changes}).model_dump()
    except ValidationError as exc:
        raise AppError(
            "INVALID_PROPOSAL", "Revisa las etiquetas y los campos de la propuesta"
        ) from exc
    changed = content != proposal.content
    target = data.status or proposal.status
    if not changed and target == proposal.status:
        session.commit()
        return proposal
    actions = allowed_actions(proposal.status, stale)
    if changed and "edit" not in actions:
        if stale:
            raise AppError("STALE_PROPOSAL", "Regenera la propuesta con las guías vigentes", 409)
        raise AppError("READ_ONLY_PROPOSAL", "Reabre la revisión antes de editar", 409)
    if target != proposal.status:
        action = {"approved": "approve", "rejected": "reject", "pending_review": "reopen"}[target]
        if action not in actions:
            code = "STALE_PROPOSAL" if stale else "INVALID_TRANSITION"
            message = (
                "Regenera la propuesta con las guías vigentes"
                if stale
                else "Reabre la revisión antes de cambiar la decisión"
            )
            raise AppError(code, message, 409)
        if target == "pending_review" and changes:
            raise AppError(
                "INVALID_TRANSITION", "Reabre sin modificar contenido en esa petición", 409
            )
        if target == "rejected" and changed:
            raise AppError(
                "INVALID_TRANSITION", "Guarda o descarta los cambios antes de rechazar", 409
            )
    proposal.content = content
    proposal.status = target
    proposal.revision += 1
    session.commit()
    return proposal
