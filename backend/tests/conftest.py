"""Test harness.

Tests run against a real Postgres database (pgvector and constraints matter for the security
rules we test). The schema is migrated once per session; each test runs inside a transaction
that is rolled back afterwards, so tests are isolated and fast.
"""

import os
from collections.abc import Iterator
from datetime import UTC, datetime

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
os.environ["PC_RESUME_PROCESSING_ON_STARTUP"] = "false"
os.environ["PC_RETENTION_SCHEDULE_ENABLED"] = "false"
# Never use the real Claude key in tests (it lives in backend/.env); a blank key disables Claude.
os.environ["ANTHROPIC_API_KEY"] = ""

from app.answers.model import GroundedAnswer, ModelReply, get_answer_model  # noqa: E402
from app.auth.security import hash_password  # noqa: E402
from app.config import Settings, get_settings  # noqa: E402
from app.db import get_db  # noqa: E402
from app.email import MemoryEmailSender, get_email_sender  # noqa: E402
from app.main import create_app  # noqa: E402
from app.models import User  # noqa: E402
from app.processing import InlineRunner, get_runner  # noqa: E402
from app.public_limits import RateLimiter, get_public_limiter  # noqa: E402
from app.rag.embeddings import HashingEmbedder, get_embedder  # noqa: E402
from app.storage import LocalStorage, get_storage  # noqa: E402


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
def storage(tmp_path) -> LocalStorage:
    return LocalStorage(tmp_path / "storage")


class RecordingRunner:
    """Default in tests: remembers submitted versions and leaves them in PROCESSING."""

    def __init__(self) -> None:
        self.submitted: list = []

    def submit(self, version_id) -> None:
        self.submitted.append(version_id)


@pytest.fixture
def runner() -> RecordingRunner:
    return RecordingRunner()


@pytest.fixture
def process_inline(app, db, storage):
    """Opt in: uploads are processed immediately, with a deterministic test embedder."""
    inline = InlineRunner(db, storage, HashingEmbedder())
    app.dependency_overrides[get_runner] = lambda: inline
    return inline


class StubAnswerModel:
    """Stand-in for Claude in API tests: answers from the first passage, recording each call.

    Tests can set `next_reply` to script a specific outcome.
    """

    def __init__(self) -> None:
        self.calls: list[tuple[str, list]] = []
        self.next_reply: ModelReply | None = None

    def answer(self, question, passages) -> ModelReply:
        self.calls.append((question, passages))
        if self.next_reply is not None:
            return self.next_reply
        return ModelReply(
            GroundedAnswer(
                sufficient=True,
                conflict=False,
                answer=f"According to the policy: {passages[0].text[:80]}",
                cited_passages=["P1"],
            ),
            None,
        )


@pytest.fixture
def answer_model() -> StubAnswerModel:
    return StubAnswerModel()


# A lower evidence threshold suits the simple test embedder's similarity scores.
TEST_SETTINGS_OVERRIDES = {"retrieval_min_score": 0.3, "escalation_min_score": 0.2}


@pytest.fixture
def public_limiter() -> RateLimiter:
    """A fresh per-test limiter with the real default limits."""
    settings = Settings()
    return RateLimiter(settings.public_questions_per_minute, settings.public_questions_per_hour)


@pytest.fixture
def app(db, mailer, storage, runner, answer_model, public_limiter):
    app = create_app()
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_email_sender] = lambda: mailer
    app.dependency_overrides[get_storage] = lambda: storage
    app.dependency_overrides[get_runner] = lambda: runner
    # Tests never call Claude or load the real embedding model.
    app.dependency_overrides[get_answer_model] = lambda: answer_model
    app.dependency_overrides[get_embedder] = lambda: HashingEmbedder()
    app.dependency_overrides[get_settings] = lambda: Settings(**TEST_SETTINGS_OVERRIDES)
    app.dependency_overrides[get_public_limiter] = lambda: public_limiter
    return app


@pytest.fixture
def client(app) -> Iterator[TestClient]:
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c


TEST_PASSWORD = "correct horse battery"


def sign_in_new_user(db, client: TestClient, email: str) -> None:
    """Create a verified user directly in the database and sign them in on this client."""
    db.add(
        User(
            email=email,
            password_hash=hash_password(TEST_PASSWORD),
            email_verified_at=datetime.now(UTC),
        )
    )
    db.flush()
    resp = client.post("/api/auth/login", json={"email": email, "password": TEST_PASSWORD})
    assert resp.status_code == 200, resp.text


@pytest.fixture
def make_client(app, db):
    """Create a separate browser (own cookies), optionally signed in as a new verified user."""
    clients: list[TestClient] = []

    def make(email: str | None = None) -> TestClient:
        c = TestClient(app, raise_server_exceptions=False)
        clients.append(c)
        if email:
            sign_in_new_user(db, c, email)
        return c

    yield make
    for c in clients:
        c.close()
