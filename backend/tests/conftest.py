import os
from pathlib import Path

import pytest

# Deterministic doubles are explicit and confined to the test process.
os.environ["LLM_PROVIDER"] = "mock"
os.environ["EMBEDDING_PROVIDER"] = "hash"
os.environ["SIMILARITY_THRESHOLD"] = "0.05"
os.environ["OTEL_ENABLED"] = "false"
if os.environ.get("TEST_DATABASE_URL"):
    os.environ["DATABASE_URL"] = os.environ["TEST_DATABASE_URL"]

from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from app.api import app  # noqa: E402
from app.config import get_settings  # noqa: E402
from app.db import get_engine  # noqa: E402
from app.schemas import Product  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import text  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402


@pytest.fixture
def product():
    return Product(
        id="P-1",
        title="BUFANDA AZUL",
        description="Bufanda de lana azul.",
        brand="Puna",
        category="textiles",
    )


@pytest.fixture(scope="session")
def database():
    if not os.environ.get("TEST_DATABASE_URL"):
        pytest.skip("Define TEST_DATABASE_URL para ejecutar integración con PostgreSQL real")
    engine = get_engine()
    if not str(engine.url.database).endswith("_test"):
        raise RuntimeError("La base de pruebas debe terminar en _test")
    command.upgrade(Config("alembic.ini"), "head")
    return engine


@pytest.fixture
def db(database):
    with database.begin() as connection:
        connection.execute(text("TRUNCATE documents, batches CASCADE"))
    with Session(database) as session:
        yield session


@pytest.fixture
def client(db, monkeypatch, tmp_path: Path):
    monkeypatch.setattr(get_settings(), "upload_dir", tmp_path)
    monkeypatch.setattr("app.api.ingest_task.apply_async", lambda **kwargs: None)
    monkeypatch.setattr("app.api.enrich_task.apply_async", lambda **kwargs: None)
    return TestClient(app)
