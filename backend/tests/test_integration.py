import json
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import Mock
from uuid import uuid4

import pytest
from app.embeddings import get_embedder
from app.errors import TransientError
from app.models import BatchItem, Chunk, DocumentVersion, Proposal
from app.processing import entity_session, ingest_version, process_item
from app.retrieval import retrieve
from app.tasks import run_task
from kombu.exceptions import OperationalError as BrokerError
from sqlalchemy import func, select

pytestmark = pytest.mark.integration


def index_guide(client, brand="Puna", category="textiles", content=None):
    content = (
        content
        or (
            "# PUNA-01\nPuna bufanda lana azul textiles. Título empieza por Puna. "
            "No inventar datos. Etiquetas en minúsculas."
        ).encode()
    )
    response = client.post(
        "/api/v1/documents",
        data={"title": "Guía Puna", "brand": brand, "category": category},
        files={"file": ("guide.md", content)},
    )
    assert response.status_code == 202, response.text
    result = response.json()
    ingest_version(result["version_id"])
    return result


def launch(client, product, key=None):
    response = client.post(
        "/api/v1/batches",
        headers={"Idempotency-Key": key or str(uuid4())},
        files={"file": ("p.json", json.dumps([product.model_dump()]).encode())},
    )
    assert response.status_code == 202, response.text
    return response.json()


def enrich(client, db, product):
    batch = launch(client, product)
    item = db.scalar(select(BatchItem).where(BatchItem.batch_id == batch["id"]))
    process_item(item.id)
    return batch, item, client.get("/api/v1/proposals").json()[0]


def test_api_ingest_retrieve_edit_approve_and_idempotency(client, db, product):
    guide = index_guide(client)
    index_guide(client, brand="Otra", content=b"# Otra\nPuna bufanda lana azul textiles.")
    evidence = retrieve(
        db,
        product,
        [doc.id for doc in db.scalars(select(DocumentVersion))],
        get_embedder(),
        threshold=0,
    )
    assert evidence and all(chunk["document_id"] == guide["document_id"] for chunk in evidence)
    first = launch(client, product, "same-key")
    second = launch(client, product, "same-key")
    assert first["id"] == second["id"]
    changed = product.model_copy(update={"title": "Otra ficha"})
    conflict = client.post(
        "/api/v1/batches",
        headers={"Idempotency-Key": "same-key"},
        files={"file": ("p.json", json.dumps([changed.model_dump()]).encode())},
    )
    assert conflict.status_code == 409
    item = db.scalar(select(BatchItem).where(BatchItem.batch_id == first["id"]))
    process_item(item.id)
    process_item(item.id)
    assert db.scalar(select(func.count()).select_from(Proposal)) == 1
    proposal = client.get("/api/v1/proposals").json()[0]
    result = client.patch(
        f"/api/v1/proposals/{proposal['id']}",
        json={
            "revision": proposal["revision"],
            "title": "Puna Bufanda de lana azul",
            "status": "approved",
        },
    )
    assert result.status_code == 200, result.text
    detail = client.get(f"/api/v1/proposals/{proposal['id']}").json()
    assert detail["status"] == "approved" and detail["citations"]
    assert detail["original"]["title"] == product.title
    # A retry after review cannot overwrite the analyst's title or approval.
    process_item(item.id)
    assert (
        client.get(f"/api/v1/proposals/{proposal['id']}").json()["content"]["title"]
        == "Puna Bufanda de lana azul"
    )
    assert client.get(f"/api/v1/batches/{first['id']}").json()["status"] == "completed"


def test_version_activation_preserves_history_and_blocks_stale_approval(client, db, product):
    guide = index_guide(client)
    _, _, proposal = enrich(client, db, product)
    response = client.post(
        f"/api/v1/documents/{guide['document_id']}/versions",
        files={"file": ("v2.md", b"# PUNA-02\nPuna bufanda lana azul textiles. Nuevo limite 70.")},
    )
    ingest_version(response.json()["version_id"])
    assert client.get(f"/api/v1/proposals/{proposal['id']}").json()["is_stale"]
    response = client.patch(
        f"/api/v1/proposals/{proposal['id']}", json={"revision": 1, "status": "approved"}
    )
    assert response.status_code == 409
    assert db.scalar(select(func.count()).select_from(Chunk)) >= 2
    assert client.get(f"/api/v1/proposals/{proposal['id']}").json()["citations"]


def test_failed_version_keeps_previous_active(client, db):
    guide = index_guide(client)
    response = client.post(
        f"/api/v1/documents/{guide['document_id']}/versions",
        files={"file": ("bad.pdf", b"%PDF-1.7\nbroken")},
    )
    task = Mock()
    run_task(task, "document", response.json()["version_id"])
    db.expire_all()
    assert db.get(DocumentVersion, guide["version_id"]).is_active
    assert db.get(DocumentVersion, response.json()["version_id"]).status == "error"


def test_no_evidence_blocks_product_and_marks_batch(client, db, product):
    batch = launch(client, product)
    item = db.scalar(select(BatchItem).where(BatchItem.batch_id == batch["id"]))
    run_task(Mock(), "item", item.id)
    result = client.get(f"/api/v1/batches/{batch['id']}").json()
    assert result["status"] == "with_errors" and result["counts"]["blocked"] == 1
    assert client.get("/api/v1/proposals").json() == []


def test_broker_failure_persists_batch_and_recovery(client, db, product, monkeypatch):
    monkeypatch.setattr(
        "app.dispatch.enrich_task.apply_async", Mock(side_effect=BrokerError("down"))
    )
    response = client.post(
        "/api/v1/batches",
        headers={"Idempotency-Key": "redis-down"},
        files={"file": ("p.json", json.dumps([product.model_dump()]).encode())},
    )
    assert response.status_code == 503
    batch_id = response.json()["error"]["batch_id"]
    assert client.get(f"/api/v1/batches/{batch_id}").json()["dispatch_error"]
    monkeypatch.setattr("app.dispatch.enrich_task.apply_async", Mock())
    assert launch(client, product, "redis-down")["id"] == batch_id
    assert client.get(f"/api/v1/batches/{batch_id}").json()["dispatch_error"] is None


def test_advisory_lock_prevents_concurrent_delivery(client, db, product):
    batch = launch(client, product)
    item = db.scalar(select(BatchItem).where(BatchItem.batch_id == batch["id"]))
    with entity_session(item.id):
        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(process_item, item.id)
            with pytest.raises(TransientError, match="ITEM_BUSY"):
                future.result()


def test_optimistic_review_conflict_and_rejection(client, db, product):
    index_guide(client)
    _, _, proposal = enrich(client, db, product)
    path = f"/api/v1/proposals/{proposal['id']}"
    assert client.patch(path, json={"revision": 1, "status": "rejected"}).status_code == 200
    assert client.patch(path, json={"revision": 1, "status": "approved"}).status_code == 409
    assert client.get(path).json()["status"] == "rejected"


@pytest.mark.parametrize("decision", ["approved", "rejected"])
def test_terminal_review_requires_explicit_reopen_and_noop_is_stable(client, db, product, decision):
    index_guide(client)
    _, _, proposal = enrich(client, db, product)
    path = f"/api/v1/proposals/{proposal['id']}"
    decided = client.patch(path, json={"revision": 1, "status": decision}).json()
    assert decided["allowed_actions"] == ["reopen"]
    content = {key: decided["content"][key] for key in ("title", "description", "tags")}
    noop = client.patch(path, json={"revision": 2, "status": decision, **content})
    assert noop.status_code == 200 and noop.json()["revision"] == 2
    assert noop.json()["status"] == decision
    assert client.patch(path, json={"revision": 2}).json()["revision"] == 2
    assert client.patch(path, json={"revision": 2, "title": "Otro título"}).status_code == 409
    other = "rejected" if decision == "approved" else "approved"
    assert client.patch(path, json={"revision": 2, "status": other}).status_code == 409
    assert (
        client.patch(path, json={"revision": 2, "status": "pending_review", **content}).status_code
        == 409
    )
    reopened = client.patch(path, json={"revision": 2, "status": "pending_review"}).json()
    assert reopened["revision"] == 3 and "edit" in reopened["allowed_actions"]
    edited = client.patch(path, json={"revision": 3, "title": "Puna Bufanda revisada"}).json()
    assert edited["revision"] == 4 and edited["status"] == "pending_review"
    assert edited["citations"] == decided["citations"]
    assert client.patch(path, json={"revision": 2, "status": "approved"}).status_code == 409


def test_reject_does_not_silently_persist_content(client, db, product):
    index_guide(client)
    _, _, proposal = enrich(client, db, product)
    path = f"/api/v1/proposals/{proposal['id']}"
    response = client.patch(path, json={"revision": 1, "status": "rejected", "title": "Borrador"})
    assert response.status_code == 409
    assert client.get(path).json()["content"] == proposal["content"]


@pytest.mark.parametrize("kind", ["item", "document"])
def test_failure_is_persisted_before_ownership_is_released(client, db, product, monkeypatch, kind):
    from threading import Event

    import app.processing as processing
    from app.errors import AppError

    if kind == "item":
        batch = launch(client, product)  # No guides: deterministic insufficient evidence.
        identifier = db.scalar(select(BatchItem.id).where(BatchItem.batch_id == batch["id"]))
        function, model, expected = process_item, BatchItem, "blocked"
    else:
        response = client.post(
            "/api/v1/documents",
            data={"title": "Corrupta"},
            files={"file": ("bad.pdf", b"%PDF-1.7\nbroken")},
        )
        identifier = response.json()["version_id"]
        function, model, expected = ingest_version, DocumentVersion, "error"
    reached, release = Event(), Event()
    original = processing.record_task_error

    def paused(*args, **kwargs):
        reached.set()
        assert release.wait(5)
        original(*args, **kwargs)

    monkeypatch.setattr(processing, "record_task_error", paused)
    with ThreadPoolExecutor(max_workers=2) as executor:
        failing = executor.submit(function, identifier)
        try:
            assert reached.wait(5)
            duplicate = executor.submit(function, identifier)
            with pytest.raises(TransientError, match="ITEM_BUSY"):
                duplicate.result(timeout=5)
        finally:
            release.set()
        with pytest.raises(AppError):
            failing.result(timeout=5)
    db.expire_all()
    assert db.get(model, identifier).status == expected


def test_manual_retry_skips_owned_work_and_preserves_success(client, db, product, monkeypatch):
    index_guide(client)
    batch, item, proposal = enrich(client, db, product)
    publisher = Mock()
    monkeypatch.setattr("app.dispatch.enrich_task.apply_async", publisher)
    db.refresh(item)
    item.status = "failed"
    db.commit()
    with entity_session(item.id):
        assert client.post(f"/api/v1/batches/{batch['id']}/retry?mode=failed").status_code == 202
        publisher.assert_not_called()
    db.refresh(item)
    assert item.status == "failed"
    # Restore the successful item; a manual recovery must not reset its proposal.
    item.status = "succeeded"
    db.commit()
    client.post(f"/api/v1/batches/{batch['id']}/retry?mode=unfinished")
    publisher.assert_not_called()
    assert client.get(f"/api/v1/proposals/{proposal['id']}").json()["revision"] == 1


def test_list_queries_remain_bounded_and_pagination_is_exact(client, db, product):
    from sqlalchemy import event

    index_guide(client)
    for number in range(4):
        enrich(client, db, product.model_copy(update={"id": f"P-{number}"}))
    statements = []

    def collect(_connection, _cursor, statement, _parameters, _context, _many):
        if statement.lstrip().upper().startswith("SELECT"):
            statements.append(statement)

    event.listen(db.bind, "before_cursor_execute", collect)
    try:
        for path in ("proposals", "batches"):
            counts = []
            for limit in (1, 4):
                statements.clear()
                result = client.get(f"/api/v1/{path}?limit={limit}")
                assert result.status_code == 200
                counts.append(len(statements))
                assert result.headers["X-Has-More"] == ("true" if limit == 1 else "false")
            assert counts[0] == counts[1] == 2
    finally:
        event.remove(db.bind, "before_cursor_execute", collect)
    ids = [row["id"] for row in client.get("/api/v1/proposals?limit=4").json()]
    paged = [
        row["id"]
        for offset in (0, 2)
        for row in client.get(f"/api/v1/proposals?limit=2&offset={offset}").json()
    ]
    assert ids == paged


def test_two_analysts_cannot_both_decide_same_revision(client, db, product):
    index_guide(client)
    _, _, proposal = enrich(client, db, product)
    path = f"/api/v1/proposals/{proposal['id']}"
    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(
            executor.map(
                lambda status: (
                    client.patch(path, json={"revision": 1, "status": status}).status_code
                ),
                ["approved", "rejected"],
            )
        )
    assert sorted(results) == [200, 409]
    assert client.get(path).json()["revision"] == 2


def test_latest_guides_and_version_history_are_independently_paginated(client, db):
    guide = index_guide(client)
    other = index_guide(client, brand="Otra")
    version = client.post(
        f"/api/v1/documents/{guide['document_id']}/versions",
        files={"file": ("v2.md", b"# Nueva\nPuna bufanda lana azul. Politica nueva.")},
    ).json()
    ingest_version(version["version_id"])
    latest = client.get("/api/v1/documents?latest_only=true&limit=1")
    assert latest.headers["X-Has-More"] == "true"
    all_latest = client.get("/api/v1/documents?latest_only=true&limit=200").json()
    assert len(all_latest) == 2
    assert {row["id"] for row in all_latest} == {guide["document_id"], other["document_id"]}
    history = client.get(f"/api/v1/documents?document_id={guide['document_id']}&limit=1")
    assert history.headers["X-Has-More"] == "true"
    assert history.json()[0]["version_id"] == version["version_id"]


def test_regeneration_requires_stale_evidence_and_keeps_decision(client, db, product):
    guide = index_guide(client)
    _, _, proposal = enrich(client, db, product)
    path = f"/api/v1/proposals/{proposal['id']}"
    client.patch(path, json={"revision": 1, "status": "approved"})
    headers = {"Idempotency-Key": "regenerate-stale"}
    assert client.post(f"{path}/regenerate", headers=headers).status_code == 409
    version = client.post(
        f"/api/v1/documents/{guide['document_id']}/versions",
        files={"file": ("v2.md", b"# Nueva\nPuna bufanda lana azul. Limite 70.")},
    ).json()
    ingest_version(version["version_id"])
    stale = client.get(path).json()
    assert stale["is_stale"] and stale["allowed_actions"] == ["regenerate"]
    first = client.post(f"{path}/regenerate", headers=headers)
    second = client.post(f"{path}/regenerate", headers=headers)
    assert first.status_code == second.status_code == 202
    assert first.json()["id"] == second.json()["id"]
    history = client.get(path).json()
    assert history["status"] == "approved" and history["revision"] == 2
    assert history["citations"] == stale["citations"]


def test_worker_persists_transient_failures_and_exhaustion_under_lock(
    client, db, product, monkeypatch
):
    from types import SimpleNamespace

    index_guide(client)
    batch = launch(client, product)
    item = db.scalar(select(BatchItem).where(BatchItem.batch_id == batch["id"]))
    monkeypatch.setattr(
        "app.processing.generate_validated", Mock(side_effect=TransientError("LLM_RATE_LIMIT"))
    )
    for retry in range(4):
        task = Mock(request=SimpleNamespace(retries=retry))
        task.retry.side_effect = RuntimeError("retry scheduled")
        if retry < 3:
            with pytest.raises(RuntimeError, match="retry scheduled"):
                run_task(task, "item", item.id)
        else:
            run_task(task, "item", item.id)
            task.retry.assert_not_called()
        db.refresh(item)
        assert item.attempts == retry + 1
        assert item.status == ("pending" if retry < 3 else "failed")
        assert item.error["retry_exhausted"] == (retry == 3)
    assert db.scalar(select(func.count()).select_from(Proposal)) == 0


def test_approval_and_activation_are_serialized(client, db, product, monkeypatch):
    from threading import Event

    import app.reviews as reviews

    guide = index_guide(client)
    _, _, proposal = enrich(client, db, product)
    version = client.post(
        f"/api/v1/documents/{guide['document_id']}/versions",
        files={"file": ("v2.md", b"# Nueva\nPuna bufanda lana azul. Limite 70.")},
    ).json()
    locked, release = Event(), Event()
    original = reviews.proposal_is_stale

    def pause_after_document_lock(session, item):
        locked.set()
        assert release.wait(5)
        return original(session, item)

    monkeypatch.setattr(reviews, "proposal_is_stale", pause_after_document_lock)
    path = f"/api/v1/proposals/{proposal['id']}"
    with ThreadPoolExecutor(max_workers=2) as executor:
        approval = executor.submit(client.patch, path, json={"revision": 1, "status": "approved"})
        try:
            assert locked.wait(5)
            activation = executor.submit(ingest_version, version["version_id"])
        finally:
            release.set()
        assert approval.result(timeout=5).status_code == 200
        activation.result(timeout=5)
    result = client.get(path).json()
    assert result["status"] == "approved" and result["is_stale"]
    assert result["allowed_actions"] == ["regenerate"]


def test_retrying_failed_items_does_not_hide_unfinished_dispatch_error(client, db, product):
    from app.models import Batch

    batch = launch(client, product)
    stored = db.get(Batch, batch["id"])
    stored.dispatch_error = {"code": "BROKER_UNAVAILABLE", "message": "Pendientes sin publicar"}
    item = db.scalar(select(BatchItem).where(BatchItem.batch_id == stored.id))
    item.status = "failed"
    db.commit()
    retried = client.post(f"/api/v1/batches/{stored.id}/retry?mode=failed")
    assert retried.status_code == 202 and retried.json()["dispatch_error"]
    recovered = client.post(f"/api/v1/batches/{stored.id}/retry?mode=unfinished")
    assert recovered.status_code == 202 and recovered.json()["dispatch_error"] is None
