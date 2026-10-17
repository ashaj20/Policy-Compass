"""RAGService: turns a stored policy version into searchable knowledge (US-011).

In-house implementation (decision A3): extraction -> passages -> embeddings in pgvector ->
validation. A hosted provider could implement the same interface later.
"""

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models import DocumentChunk, PolicyVersion
from app.rag.chunking import chunk_blocks
from app.rag.embeddings import Embedder
from app.rag.extract import ProcessingFailed, extract_blocks
from app.storage import Storage

SELF_MATCH_MIN_SIMILARITY = 0.5


class RAGService:
    def __init__(self, db: Session, storage: Storage, embedder: Embedder):
        self.db = db
        self.storage = storage
        self.embedder = embedder

    def ingest_version(self, version: PolicyVersion, on_stage=lambda stage: None) -> int:
        """Extract, chunk, embed and validate one version. Returns the number of passages.

        Re-running replaces any earlier passages for this version, so a retry never leaves
        duplicates behind (US-012). Raises ProcessingFailed with a safe message on bad input.
        """
        on_stage("EXTRACTING")
        blocks = extract_blocks(self.storage.read(version.storage_key), version.content_type)

        on_stage("CHUNKING")
        chunks = chunk_blocks(blocks)
        if not chunks:
            raise ProcessingFailed("We couldn't find any passages of text to make searchable.")

        on_stage("INDEXING")
        # Including the section heading helps questions find the right passage.
        vectors = self.embedder.embed(
            [f"{c.section}\n{c.text}" if c.section else c.text for c in chunks]
        )
        self.db.execute(delete(DocumentChunk).where(DocumentChunk.version_id == version.id))
        for chunk, vector in zip(chunks, vectors, strict=True):
            self.db.add(
                DocumentChunk(
                    organisation_id=version.organisation_id,
                    policy_id=version.policy_id,
                    version_id=version.id,
                    chunk_index=chunk.index,
                    section=chunk.section,
                    page=chunk.page,
                    text=chunk.text,
                    embedding=vector,
                )
            )
        self.db.flush()

        on_stage("VALIDATING")
        self._validate(version, vectors[0], len(chunks))
        return len(chunks)

    def _validate(self, version: PolicyVersion, probe: list[float], expected: int) -> None:
        """REVIEW C1: passages were stored, and a search for the document's own text finds it."""
        stored = self.db.scalar(
            select(DocumentChunk.id).where(DocumentChunk.version_id == version.id).limit(1)
        )
        if stored is None:
            raise ProcessingFailed("The document couldn't be made searchable.")
        distance = DocumentChunk.embedding.cosine_distance(probe)
        best = self.db.execute(
            select(DocumentChunk.version_id, distance.label("distance"))
            .where(DocumentChunk.version_id == version.id)
            .order_by(distance)
            .limit(1)
        ).first()
        if best is None or (1 - best.distance) < SELF_MATCH_MIN_SIMILARITY:
            raise ProcessingFailed("The document was indexed but couldn't be found by search.")
        count = self.db.query(DocumentChunk).filter(DocumentChunk.version_id == version.id).count()
        if count != expected:
            raise ProcessingFailed("The document was only partly indexed.")
