import logging
import random
from typing import Any

from billiard.exceptions import SoftTimeLimitExceeded
from celery import Celery
from celery.signals import setup_logging, worker_process_init
from opentelemetry import trace
from opentelemetry.trace import Status, StatusCode
from sqlalchemy.exc import InterfaceError, OperationalError

from app.config import get_settings
from app.db import get_engine
from app.errors import AppError, TransientError
from app.processing import ingest_version, process_item
from app.telemetry import configure_logging, configure_telemetry

settings = get_settings()
celery_app = Celery("andinarag", broker=settings.redis_url)
celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    task_ignore_result=True,
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,
    worker_concurrency=2,
    broker_connection_retry_on_startup=True,
    broker_connection_timeout=2,
    broker_transport_options={
        "visibility_timeout": 300,
        "socket_connect_timeout": 2,
        "socket_timeout": 2,
        "retry_on_timeout": False,
    },
    task_publish_retry=False,
    task_soft_time_limit=110,
    task_time_limit=120,
    worker_hijack_root_logger=False,
)
logger = logging.getLogger(__name__)


@setup_logging.connect
def initialize_logging(**kwargs: Any) -> None:
    configure_logging()


@worker_process_init.connect
def initialize_worker(**kwargs: Any) -> None:
    # Never share inherited pooled connections or exporter threads with child processes.
    get_engine().dispose(close=False)
    configure_telemetry("andinarag-worker")


def retry_delay(retries: int, retry_after: float | None = None) -> float:
    if retry_after is not None:
        return max(0.0, min(60.0, retry_after))
    return random.uniform(0.5, 1.0) * min(30, 2 ** (retries + 1))


def run_task(task: Any, kind: str, entity_id: str) -> None:
    retries = task.request.retries if isinstance(task.request.retries, int) else 0
    exhausted = retries >= 3
    try:
        (process_item if kind == "item" else ingest_version)(entity_id, retries_exhausted=exhausted)
    except (TransientError, OperationalError, InterfaceError, SoftTimeLimitExceeded) as exc:
        code = exc.code if isinstance(exc, TransientError) else "INFRASTRUCTURE_UNAVAILABLE"
        if code == "ITEM_BUSY":
            # Another delivery owns the lock. Never change its state or retry budget.
            if not exhausted:
                raise task.retry(
                    exc=exc, countdown=retry_delay(task.request.retries), max_retries=3
                ) from exc
            return
        logger.warning(
            "task_retry",
            extra={"entity_id": entity_id, "error_code": code, "retry": task.request.retries},
        )
        trace.get_current_span().set_status(Status(StatusCode.ERROR, code))
        if not exhausted:
            raise task.retry(
                exc=TransientError(code),
                countdown=retry_delay(
                    task.request.retries,
                    exc.retry_after if isinstance(exc, TransientError) else None,
                ),
                max_retries=3,
            ) from exc
    except AppError as exc:
        trace.get_current_span().set_status(Status(StatusCode.ERROR, exc.code))
        logger.warning("task_failed", extra={"entity_id": entity_id, "error_code": exc.code})
    except Exception:
        trace.get_current_span().set_status(Status(StatusCode.ERROR, "INTERNAL_ERROR"))
        logger.error("task_failed", extra={"entity_id": entity_id, "error_code": "INTERNAL_ERROR"})


@celery_app.task(bind=True, name="andina.ingest")
def ingest_task(self: Any, version_id: str) -> None:
    run_task(self, "document", version_id)


@celery_app.task(bind=True, name="andina.enrich")
def enrich_task(self: Any, item_id: str) -> None:
    run_task(self, "item", item_id)
