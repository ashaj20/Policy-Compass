"""Text extraction from policy documents, keeping section headings (US-011).

Produces a flat list of blocks; each is either a heading or a paragraph, with the page it came
from (PDF only). Headings let answers cite the section a passage belongs to (Spec §13).
"""

import io
import re
from dataclasses import dataclass

import docx
from pypdf import PdfReader
from pypdf.errors import PdfReadError

from app.policies.validation import DOCX, PDF


class ProcessingFailed(Exception):
    """A document problem with a message that is safe to show to administrators."""


@dataclass
class Block:
    text: str
    is_heading: bool = False
    page: int | None = None


# "4. Reporting a repair", "4.2 Out of hours", "Section 3 - Eligibility", "APPENDIX A"
_NUMBERED = re.compile(r"^(section\s+)?\d+(\.\d+)*[.)]?\s+\S", re.IGNORECASE)


def _looks_like_heading(line: str) -> bool:
    words = line.split()
    if not words or len(line) > 90 or len(words) > 12:
        return False
    if line.endswith((".", ",", ";", ":")) and not _NUMBERED.match(line):
        return False
    if _NUMBERED.match(line):
        return True
    letters = [c for c in line if c.isalpha()]
    if letters and all(c.isupper() for c in letters) and len(letters) > 3:
        return True
    # Title Case lines such as "Reporting A Repair" or "Emergency Response Times".
    significant = [w for w in words if len(w) > 3]
    return bool(significant) and all(w[0].isupper() for w in significant) and len(words) <= 8


def _from_pdf(data: bytes) -> list[Block]:
    try:
        reader = PdfReader(io.BytesIO(data))
        if reader.is_encrypted:
            raise ProcessingFailed(
                "This PDF is password-protected. Upload a version without a password."
            )
        blocks: list[Block] = []
        for number, page in enumerate(reader.pages, start=1):
            paragraph: list[str] = []
            for raw in (page.extract_text() or "").splitlines():
                line = " ".join(raw.split())
                if not line:
                    if paragraph:
                        blocks.append(Block(" ".join(paragraph), page=number))
                        paragraph = []
                    continue
                if _looks_like_heading(line):
                    if paragraph:
                        blocks.append(Block(" ".join(paragraph), page=number))
                        paragraph = []
                    blocks.append(Block(line, is_heading=True, page=number))
                else:
                    paragraph.append(line)
            if paragraph:
                blocks.append(Block(" ".join(paragraph), page=number))
        return blocks
    except ProcessingFailed:
        raise
    except (PdfReadError, ValueError, KeyError, TypeError) as exc:
        raise ProcessingFailed(
            "We couldn't read this PDF. It may be damaged; try saving it again and re-uploading."
        ) from exc


def _from_docx(data: bytes) -> list[Block]:
    try:
        document = docx.Document(io.BytesIO(data))
    except Exception as exc:  # python-docx raises a variety of errors for damaged files
        raise ProcessingFailed(
            "We couldn't read this Word document. It may be damaged; try saving it again and "
            "re-uploading."
        ) from exc
    blocks: list[Block] = []
    for paragraph in document.paragraphs:
        text = " ".join(paragraph.text.split())
        if not text:
            continue
        style = (paragraph.style.name if paragraph.style is not None else "") or ""
        is_heading = style.startswith(("Heading", "Title")) or (
            len(text) < 90 and _NUMBERED.match(text) is not None
        )
        blocks.append(Block(text, is_heading=is_heading))
    for table in document.tables:
        for row in table.rows:
            cells = [" ".join(c.text.split()) for c in row.cells]
            line = " | ".join(c for c in cells if c)
            if line:
                blocks.append(Block(line))
    return blocks


MIN_TEXT_CHARS = 50


def extract_blocks(data: bytes, content_type: str) -> list[Block]:
    if content_type == PDF:
        blocks = _from_pdf(data)
    elif content_type == DOCX:
        blocks = _from_docx(data)
    else:
        raise ProcessingFailed("This file type isn't supported. Upload a PDF or Word document.")
    text_chars = sum(len(b.text) for b in blocks if not b.is_heading)
    if text_chars < MIN_TEXT_CHARS:
        raise ProcessingFailed(
            "We couldn't find enough text in this document. If it is a scanned image, upload a "
            "text-based PDF or Word version instead."
        )
    return blocks
