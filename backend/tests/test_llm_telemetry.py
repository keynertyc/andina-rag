"""Telemetry must preserve useful failures without exporting untrusted model data."""

import json
from unittest.mock import MagicMock, Mock

import httpx
import pytest
from app.config import get_settings
from app.errors import AppError, TransientError
from app.llm import GeminiProvider, LLMResult, generate_validated
from google.genai import errors
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.trace import StatusCode
from pydantic import SecretStr

PRIVATE_MARKER = "PRIVATE_PROVIDER_CONTENT_MUST_NOT_BE_EXPORTED"


@pytest.fixture
def exported_traces(monkeypatch):
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    tracer = provider.get_tracer("privacy-regression")
    monkeypatch.setattr("app.llm.tracer", tracer)
    monkeypatch.setattr(get_settings(), "gemini_api_key", SecretStr("test-not-a-real-key"))
    yield tracer, exporter
    provider.shutdown()


def assert_safe_failure(exporter):
    spans = exporter.get_finished_spans()
    assert any(span.status.status_code is StatusCode.ERROR for span in spans)
    events = [dict(event.attributes or {}) for span in spans for event in span.events]
    assert any(event.get("exception.stacktrace") for event in events)
    payload = json.dumps(events)
    assert PRIVATE_MARKER not in payload


def test_invalid_output_is_not_exported_in_child_or_parent_exception(exported_traces, product):
    tracer, exporter = exported_traces
    provider = Mock()
    provider.generate.return_value = LLMResult(
        json.dumps(
            {
                "title": [PRIVATE_MARKER],
                "description": "x",
                "tags": ["x"],
                "citations": ["c1"],
            }
        )
    )
    with pytest.raises(AppError, match="no validó"):
        with tracer.start_as_current_span("worker"):
            generate_validated(provider, product, [{"id": "c1", "text": "rule"}])
    assert provider.generate.call_count == 2
    assert_safe_failure(exporter)


@pytest.mark.parametrize("failure", ["timeout", 400, 429, 503])
def test_provider_error_does_not_export_private_response(
    exported_traces, product, monkeypatch, failure
):
    tracer, exporter = exported_traces
    client = MagicMock()
    factory = MagicMock()
    factory.return_value.__enter__.return_value = client
    monkeypatch.setattr("google.genai.Client", factory)
    client.models.generate_content.side_effect = (
        httpx.ReadTimeout(PRIVATE_MARKER)
        if failure == "timeout"
        else errors.APIError(failure, {"error": {"message": PRIVATE_MARKER}})
    )
    expected = AppError if failure == 400 else TransientError
    with pytest.raises(expected):
        with tracer.start_as_current_span("worker"):
            generate_validated(GeminiProvider(), product, [{"id": "c1", "text": "rule"}])
    assert_safe_failure(exporter)
