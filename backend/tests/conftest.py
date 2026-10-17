"""Test harness.

Tests run against a real Postgres database (pgvector and constraints matter for the security
rules we test). The schema is migrated once per session; each test runs inside a transaction
that is rolled back afterwards, so tests are isolated and fast.
"""

import os
from collections.abc import Iterator

import pytest
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from alembic import command

TEST_DATABASE_URL = os.environ.get(
    "PC_TEST_DATABASE_URL", "postgresql+psycopg://pc:pc@localhost:5432/policy_compass_test"
)
os.environ["PC_DATABASE_URL"] = TEST_DATABASE_URL
os.environ.setdefault("PC_ENVIRONMENT", "test")

from app.db import get_db  # noqa: E402
from app.email import MemoryEmailSender, get_email_sender  # noqa: E402
from app.main import create_app  # noqa: E402


@pytest.fixture(scope="session")
def engine():
    engine = create_engine(TEST_DATABASE_URL)
    with engine.begin() as conn:
        conn.execute(text("DROP SCHEMA public CASCADE; CREATE SCHEMA public;"))
    cfg = Config(os.path.join(os.path.dirname(__file__), "..", "alembic.ini"))
    cfg.set_main_option("sqlalchemy.url", TEST_DATABASE_URL)
    command.upgrade(cfg, "head")
    yield engine
    engine.dispose()


@pytest.fixture
def db(engine) -> Iterator[Session]:
    connection = engine.connect()
    transaction = connection.begin()
    session = Session(bind=connection, join_transaction_mode="create_savepoint")
    try:
        yield session
    finally:
        session.close()
        transaction.rollback()
        connection.close()


@pytest.fixture
def mailer() -> MemoryEmailSender:
    return MemoryEmailSender()


@pytest.fixture
def app(db, mailer):
    app = create_app()
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_email_sender] = lambda: mailer
    return app


@pytest.fixture
def client(app) -> Iterator[TestClient]:
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c
