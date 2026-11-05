import logging

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.celery import CeleryInstrumentor
from opentelemetry.instrumentation.logging import LoggingInstrumentor
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from pythonjsonlogger.json import JsonFormatter

from app.config import get_settings
from app.db import get_engine

tracer = trace.get_tracer("andinarag")


def configure_logging() -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(
        JsonFormatter(
            "%(asctime)s %(levelname)s %(name)s %(message)s %(otelTraceID)s %(otelSpanID)s",
            rename_fields={"otelTraceID": "trace_id", "otelSpanID": "span_id"},
        )
    )
    logging.basicConfig(level=logging.INFO, handlers=[handler], force=True)
    LoggingInstrumentor().instrument(set_logging_format=False, inject_trace_context=True)


def configure_telemetry(service: str) -> None:
    configure_logging()
    if not get_settings().otel_enabled:
        return
    provider = TracerProvider(resource=Resource.create({"service.name": service}))
    provider.add_span_processor(
        BatchSpanProcessor(
            OTLPSpanExporter(
                endpoint=get_settings().otel_exporter_otlp_endpoint.rstrip("/") + "/v1/traces",
                timeout=3,
            )
        )
    )
    trace.set_tracer_provider(provider)
    CeleryInstrumentor().instrument()
    SQLAlchemyInstrumentor().instrument(engine=get_engine())
