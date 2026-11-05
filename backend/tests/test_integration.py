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
    monkeypatch.setattr("app.api.enrich_task.apply_async", Mock(side_effect=BrokerError("down")))
    response = client.post(
        "/api/v1/batches",
        headers={"Idempotency-Key": "redis-down"},
        files={"file": ("p.json", json.dumps([product.model_dump()]).encode())},
    )
    assert response.status_code == 503
    batch_id = response.json()["error"]["batch_id"]
    assert client.get(f"/api/v1/batches/{batch_id}").json()["dispatch_error"]
    monkeypatch.setattr("app.api.enrich_task.apply_async", Mock())
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
