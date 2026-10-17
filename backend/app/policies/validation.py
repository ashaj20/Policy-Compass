"""Policy upload checks (US-006; hardened further in US-038).

The file type is decided from the file's contents, never trusted from its name or the browser's
MIME type, and the uploaded filename is only ever used for display.
"""

import io
import re
import unicodedata
import zipfile
from dataclasses import dataclass
from datetime import date

PDF = "application/pdf"
DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
ALLOWED_EXTENSIONS = {".pdf": PDF, ".docx": DOCX}

UNSUPPORTED = "This file type isn't supported. Upload a PDF or Word (.docx) document."


@dataclass
class DetectedFile:
    content_type: str
    extension: str


class FileRejected(ValueError):
    pass


def _looks_like_docx(data: bytes) -> bool:
    if not data.startswith(b"PK\x03\x04"):
        return False
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            names = set(z.namelist())
    except zipfile.BadZipFile:
        return False
    return "[Content_Types].xml" in names and "word/document.xml" in names


def detect_policy_file(filename: str, data: bytes, max_bytes: int) -> DetectedFile:
    if not data:
        raise FileRejected("The file is empty. Choose a PDF or Word document.")
    if len(data) > max_bytes:
        raise FileRejected(f"The file must be {max_bytes // (1024 * 1024)} MB or smaller.")

    extension = ("." + filename.rsplit(".", 1)[-1].lower()) if "." in filename else ""
    if extension not in ALLOWED_EXTENSIONS:
        raise FileRejected(UNSUPPORTED)

    if extension == ".pdf" and b"%PDF-" in data[:1024]:
        return DetectedFile(PDF, "pdf")
    if extension == ".docx" and _looks_like_docx(data):
        return DetectedFile(DOCX, "docx")
    # Extension and contents disagree, or the file is damaged.
    raise FileRejected(
        "This file doesn't look like a valid PDF or Word document. It may be damaged or "
        "renamed from another type."
    )


def display_filename(filename: str) -> str:
    """A safe name to show people: no path, no control characters, sensible length."""
    name = re.split(r"[\\/]", filename or "")[-1]
    name = "".join(ch for ch in name if unicodedata.category(ch)[0] != "C").strip()
    return (name or "document")[:200]


# --- Metadata ---

VERSION_PATTERN = re.compile(r"^[0-9A-Za-z][0-9A-Za-z.\-]*$")


def check_policy_name(value: str) -> str:
    value = " ".join((value or "").split())
    if not value:
        raise ValueError("Enter the policy name")
    if len(value) > 200:
        raise ValueError("Use no more than 200 characters")
    return value


def check_version_label(value: str) -> str:
    value = (value or "").strip()
    if not value:
        raise ValueError("Enter the version, for example 2.1")
    if len(value) > 20:
        raise ValueError("Use no more than 20 characters")
    if not VERSION_PATTERN.match(value):
        raise ValueError("Use letters, numbers, dots and hyphens only, for example 2.1")
    return value


def check_category(value: str) -> str:
    value = " ".join((value or "").split())
    if not value:
        raise ValueError("Enter a category, for example Repairs")
    if len(value) > 60:
        raise ValueError("Use no more than 60 characters")
    return value


def check_source(value: str | None) -> str | None:
    value = " ".join((value or "").split())
    if len(value) > 300:
        raise ValueError("Use no more than 300 characters")
    return value or None


def check_effective_date(value: date) -> date:
    if not (date(1990, 1, 1) <= value <= date(2100, 12, 31)):
        raise ValueError("Enter a real effective date")
    return value
