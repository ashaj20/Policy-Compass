"""Split extracted blocks into searchable passages, each tagged with its section (US-011)."""

import re
from dataclasses import dataclass

from app.rag.extract import Block

MAX_CHARS = 1000

_SENTENCE_END = re.compile(r"(?<=[.!?])\s+")


@dataclass
class Chunk:
    index: int
    text: str
    section: str | None
    page: int | None


def _pieces(text: str) -> list[str]:
    """Break an over-long paragraph at sentence boundaries."""
    if len(text) <= MAX_CHARS:
        return [text]
    pieces, current = [], ""
    for sentence in _SENTENCE_END.split(text):
        if current and len(current) + len(sentence) + 1 > MAX_CHARS:
            pieces.append(current)
            current = ""
        while len(sentence) > MAX_CHARS:  # a single huge "sentence"
            pieces.append(sentence[:MAX_CHARS])
            sentence = sentence[MAX_CHARS:]
        current = f"{current} {sentence}".strip()
    if current:
        pieces.append(current)
    return pieces


def chunk_blocks(blocks: list[Block]) -> list[Chunk]:
    """Group paragraphs under their heading into passages of up to ~1000 characters.

    A passage never spans two sections, so each one cites exactly one section.
    """
    chunks: list[Chunk] = []
    section: str | None = None
    buffer: list[str] = []
    page: int | None = None

    def flush() -> None:
        nonlocal buffer, page
        if buffer:
            chunks.append(Chunk(len(chunks), "\n\n".join(buffer), section, page))
        buffer, page = [], None

    for block in blocks:
        if block.is_heading:
            flush()
            section = block.text[:300]
            continue
        for piece in _pieces(block.text):
            if buffer and sum(len(b) for b in buffer) + len(piece) > MAX_CHARS:
                flush()
            if page is None:
                page = block.page
            buffer.append(piece)
    flush()
    return chunks
