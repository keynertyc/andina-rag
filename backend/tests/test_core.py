import json
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from app.api import app
from app.embeddings import RegexTokenizer
from app.errors import AppError, TransientError
from app.imports import parse_products, request_fingerprint
from app.ingestion import Section, chunk_sections, extract_sections, validate_source
from app.llm import LLMResult, MockProvider, generate_validated
from app.schemas import GeneratedProposal
from app.tasks import retry_delay, run_task
from fastapi.testclient import TestClient
from pydantic import ValidationError


def test_chunking_preserves_tokens_overlap_and_location():
    text = " ".join(f"palabra{i}" for i in range(1000))
    chunks = chunk_sections([Section(text, page=3, heading="Reglas")], RegexTokenizer(), 100, 20)
    assert len(chunks) > 1
    assert all(len(chunk.text.split()) <= 100 for chunk in chunks)
    assert chunks[0].text.split()[-20:] == chunks[1].text.split()[:20]
    assert chunks[-1].text.endswith("palabra999")
    assert all(chunk.page == 3 and chunk.heading == "Reglas" for chunk in chunks)


def test_chunking_paragraph_boundary_and_empty_input():
    text = " ".join(["a"] * 70) + "\n\n" + " ".join(["b"] * 70)
    chunks = chunk_sections([Section(text)], RegexTokenizer(), 100, 10)
    assert set(chunks[0].text.split()) == {"a"}
    assert chunk_sections([Section("   ")], RegexTokenizer()) == []
    with pytest.raises(ValueError):
        chunk_sections([], RegexTokenizer(), 10, 10)


def test_markdown_sections_keep_heading():
    sections = extract_sections("guide.md", b"# Regla A\nTexto A\n\n## Regla B\nTexto B")
    assert [section.heading for section in sections] == ["Regla A", "Regla B"]


def test_document_title_alone_is_not_indexed_as_evidence():
    sections = extract_sections("guide.md", b"# Puna\n\n## Regla\nContenido verificable.")
    assert len(sections) == 1
    assert sections[0].heading == "Regla"
    with pytest.raises(AppError, match="no contiene texto"):
        extract_sections("guide.md", b"# Puna\n\n## Solo titulo")


@pytest.mark.parametrize(
    "filename,content,code",
    [
        ("image.png", b"abc", "UNSUPPORTED_FILE"),
        ("fake.pdf", b"not pdf", "INVALID_PDF"),
        ("guide.md", b"\xff", "INVALID_ENCODING"),
        ("guide.md", b"\x00bad", "INVALID_MARKDOWN"),
    ],
)
def test_file_validation(filename, content, code):
    with pytest.raises(AppError) as error:
        validate_source(filename, content)
    assert error.value.code == code


def test_corrupt_pdf_has_explicit_error():
    with pytest.raises(AppError) as error:
        extract_sections("broken.pdf", b"%PDF-1.7\ninvalid")
    assert error.value.code == "CORRUPT_DOCUMENT"


def test_structured_output_rejects_extra_fields_and_duplicates():
    with pytest.raises(ValidationError):
        GeneratedProposal(
            title="Hola", description="Texto", tags=["tag", "tag"], citations=["c1"], injected="bad"
        )


def test_invalid_output_retries_only_once(product):
    valid = MockProvider().generate(product, [{"id": "c1", "text": "regla"}]).text
    provider = Mock()
    provider.generate.side_effect = [LLMResult('{"title":"incomplete"}'), LLMResult(valid)]
    result = generate_validated(provider, product, [{"id": "c1", "text": "regla"}])
    assert result.citations == ["c1"]
    assert provider.generate.call_count == 2
    assert provider.generate.call_args.args[2] is not None


def test_hallucinated_citations_fail_after_two_attempts(product):
    provider = Mock()
    provider.generate.return_value = LLMResult(
        json.dumps(
            {
                "title": "Puna Bufanda",
                "description": "Lana azul",
                "tags": ["textiles"],
                "citations": ["invented"],
            }
        )
    )
    with pytest.raises(AppError, match="no validó"):
        generate_validated(provider, product, [{"id": "real", "text": "regla"}])
    assert provider.generate.call_count == 2


def test_no_evidence_never_calls_llm(product):
    provider = Mock()
    with pytest.raises(AppError) as error:
        generate_validated(provider, product, [])
    assert error.value.code == "INSUFFICIENT_EVIDENCE"
    provider.generate.assert_not_called()


def test_retry_backoff_bounds_and_retry_after():
    assert 1 <= retry_delay(0) <= 2
    assert 4 <= retry_delay(2) <= 8
    assert retry_delay(10) <= 30
    assert retry_delay(1, 200) == 60
    assert retry_delay(1, -1) == 0


def test_transient_failure_retries_and_exhausts(monkeypatch):
    monkeypatch.setattr(
        "app.tasks.process_item", Mock(side_effect=TransientError("LLM_RATE_LIMIT"))
    )
    save = Mock()
    monkeypatch.setattr("app.tasks.save_error", save)
    task = Mock(request=SimpleNamespace(retries=0))
    task.retry.side_effect = RuntimeError("retry scheduled")
    with pytest.raises(RuntimeError, match="retry scheduled"):
        run_task(task, "item", "item-id")
    assert save.call_args.args[2] == "pending"
    task.request.retries = 3
    task.retry.reset_mock()
    run_task(task, "item", "item-id")
    assert save.call_args.args[2] == "failed"
    task.retry.assert_not_called()


def test_duplicate_busy_task_cannot_overwrite_owner(monkeypatch):
    monkeypatch.setattr("app.tasks.process_item", Mock(side_effect=TransientError("ITEM_BUSY")))
    save = Mock()
    monkeypatch.setattr("app.tasks.save_error", save)
    run_task(Mock(request=SimpleNamespace(retries=3)), "item", "id")
    save.assert_not_called()


def test_product_import_and_idempotency_fingerprint(product):
    content = json.dumps([product.model_dump()]).encode()
    assert parse_products("p.json", content) == [product]
    assert request_fingerprint([product]) == request_fingerprint(parse_products("p.json", content))
    with pytest.raises(AppError) as error:
        parse_products("p.json", json.dumps([product.model_dump()] * 2).encode())
    assert error.value.details["rows"][0]["code"] == "DUPLICATE_PRODUCT_ID"


def test_request_body_limit_precedes_parsing():
    response = TestClient(app).post("/api/v1/documents", content=b"x" * (11 * 1024 * 1024 + 1))
    assert response.status_code == 413


def test_malformed_product_json_returns_validation_error():
    with pytest.raises(AppError):
        parse_products("p.json", b'{"not":"array"}')
