"""Running document processing in the background (US-011).

After an upload is saved, its version is handed to a runner. The default runner works through
versions one at a time on a background thread, each with its own database session. Tests use
an inline runner so processing happens synchronously inside the test's transaction.
"""

import logging
import uuid
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from functools import lru_cache
from typing import Protocol

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models import DocumentChunk, PolicyVersion, VersionStatus
from app.rag.embeddings import Embedder, get_embedder
from app.rag.extract import ProcessingFailed
from app.rag.service import RAGService
from app.storage import Storage, get_storage

logger = logging.getLogger("policy_compass.processing")

GENERIC_FAILURE = (
    "Something went wrong while preparing this document for search. Your original document "
    "has not been deleted."
)


def process_version(db: Session, version_id, storage: Storage, embedder: Embedder) -> None:
    """Process one version. Success -> DRAFT (awaiting review). Any failure -> FAILED.

    Only a version still in PROCESSING is touched, and a failure only ever changes this
    version, so the policy's active version is never affected (AC-04).
    """
    version = db.scalar(
        select(PolicyVersion).where(PolicyVersion.id == version_id).with_for_update()
    )
    if version is None or version.status != VersionStatus.PROCESSING:
        return

    def on_stage(stage: str) -> None:
        # Saved straight away so administrators can see progress while it runs.
        version.processing_stage = stage
        db.commit()

    try:
        count = RAGService(db, storage, embedder).ingest_version(version, on_stage)
    except ProcessingFailed as exc:
        db.rollback()
        _fail(db, version_id, str(exc), None)
        return
    except Exception:
        db.rollback()
        error_id = uuid.uuid4().hex[:12]
        logger.exception("Processing failed for version %s (error %s)", version_id, error_id)
        _fail(db, version_id, GENERIC_FAILURE, error_id)
        return

    version.status = VersionStatus.DRAFT
    version.processing_stage = "DONE"
    version.processed_at = datetime.now(UTC)
    version.chunk_count = count
    version.failure_reason = None
    version.error_id = None
    db.commit()


def _fail(db: Session, version_id, reason: str, error_id: str | None) -> None:
    version = db.get(PolicyVersion, version_id)
    if version is None or version.status != VersionStatus.PROCESSING:
        return
    # Nothing from a failed version may remain searchable.
    db.execute(delete(DocumentChunk).where(DocumentChunk.version_id == version_id))
    version.status = VersionStatus.FAILED
    version.failure_reason = reason
    version.error_id = error_id
    version.processed_at = datetime.now(UTC)
    db.commit()


class ProcessingRunner(Protocol):
    def submit(self, version_id) -> None: ...


class ThreadRunner:
    """One background worker, so heavy documents don't compete for memory."""

    def __init__(
        self, session_factory: Callable[[], Session], storage: Storage, embedder: Embedder
    ):
        self.session_factory = session_factory
        self.storage = storage
        self.embedder = embedder
        self.pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="processing")

    def submit(self, version_id) -> None:
        self.pool.submit(self._run, version_id)

    def _run(self, version_id) -> None:
        with self.session_factory() as db:
            try:
                process_version(db, version_id, self.storage, self.embedder)
            except Exception:
                logger.exception("Processing worker crashed for version %s", version_id)


class InlineRunner:
    """Processes immediately in the caller's session (tests and scripts)."""

    def __init__(self, db: Session, storage: Storage, embedder: Embedder):
        self.db = db
        self.storage = storage
        self.embedder = embedder

    def submit(self, version_id) -> None:
        process_version(self.db, version_id, self.storage, self.embedder)


@lru_cache
def get_runner() -> ProcessingRunner:
    from app.db import SessionLocal

    return ThreadRunner(SessionLocal, get_storage(), get_embedder())


def resume_unfinished(session_factory: Callable[[], Session], runner: ProcessingRunner) -> int:
    """Re-queue versions left in PROCESSING (e.g. the server restarted mid-way)."""
    with session_factory() as db:
        ids = list(
            db.scalars(
                select(PolicyVersion.id).where(PolicyVersion.status == VersionStatus.PROCESSING)
            )
        )
    for version_id in ids:
        runner.submit(version_id)
    return len(ids)
