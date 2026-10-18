"""Policy upload checks (US-006, hardened in US-038).

The file type is decided from the file's contents, and the browser's declared type and the
extension must agree with it. The uploaded filename is only ever used for display; storage
keys are generated (see app.storage). Word files are inspected as zip containers without being
extracted, with limits that defeat zip bombs; PDFs carrying scripts, launch actions or attached
files are refused because policy documents never need them.
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

# Browser-declared types we accept for each extension. Many browsers send a generic type, so
# octet-stream and empty are allowed; anything clearly different (HTML, images...) is refused.
GENERIC_TYPES = {"", "application/octet-stream", "binary/octet-stream"}
DECLARED_TYPES = {
    ".pdf": {PDF, "application/x-pdf", "application/acrobat"} | GENERIC_TYPES,
    ".docx": {DOCX, "application/zip", "application/x-zip-compressed"} | GENERIC_TYPES,
}

# Zip-bomb and abuse limits for Word documents.
DOCX_MAX_ENTRIES = 2000
DOCX_MAX_UNCOMPRESSED = 200 * 1024 * 1024
DOCX_MAX_RATIO = 200

# PDF features that policy documents never need and that malware commonly uses.
PDF_FORBIDDEN = (b"/JavaScript", b"/JS ", b"/JS(", b"/JS<", b"/Launch", b"/EmbeddedFile")

UNSUPPORTED = "This file type isn't supported. Upload a PDF or Word (.docx) document."
DAMAGED = (
    "This file doesn't look like a valid PDF or Word document. It may be damaged or renamed "
    "from another type."
)


@dataclass
class DetectedFile:
    content_type: str
    extension: str


class FileRejected(ValueError):
    pass


def _check_docx(data: bytes) -> None:
    """Inspect a .docx container without extracting it. Raises FileRejected."""
    if not data.startswith(b"PK\x03\x04"):
        raise FileRejected(DAMAGED)
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            infos = z.infolist()
    except (zipfile.BadZipFile, ValueError, OSError):
        raise FileRejected(DAMAGED) from None

    if len(infos) > DOCX_MAX_ENTRIES:
        raise FileRejected("This Word document has an unusual structure and can't be accepted.")
    total = sum(i.file_size for i in infos)
    compressed = sum(i.compress_size for i in infos) or 1
    if total > DOCX_MAX_UNCOMPRESSED or total / compressed > DOCX_MAX_RATIO:
        raise FileRejected("This Word document has an unusual structure and can't be accepted.")
    names = {i.filename for i in infos}
    for name in names:
        if name.startswith(("/", "\\")) or ".." in name.replace("\\", "/").split("/"):
            raise FileRejected("This Word document has an unusual structure and can't be accepted.")
    if "[Content_Types].xml" not in names or "word/document.xml" not in names:
        raise FileRejected(DAMAGED)
    if any(n.lower().endswith("vbaproject.bin") for n in names):
        raise FileRejected(
            "This Word document contains macros, which aren't allowed. Save it as a plain .docx "
            "without macros and upload it again."
        )


def _check_pdf(data: bytes) -> None:
    if b"%PDF-" not in data[:1024]:
        raise FileRejected(DAMAGED)
    if any(marker in data for marker in PDF_FORBIDDEN):
        raise FileRejected(
            "This PDF contains scripts or attached files, which aren't allowed in policy "
            "documents. Save or print it as a plain PDF and upload it again."
        )


def file_extension(filename: str) -> str:
    name = display_filename(filename)
    return ("." + name.rsplit(".", 1)[-1].lower()) if "." in name else ""


def detect_policy_file(
    filename: str, data: bytes, max_bytes: int, declared_type: str | None = None
) -> DetectedFile:
    if not data:
        raise FileRejected("The file is empty. Choose a PDF or Word document.")
    if len(data) > max_bytes:
        raise FileRejected(f"The file must be {max_bytes // (1024 * 1024)} MB or smaller.")

    extension = file_extension(filename)
    if extension not in ALLOWED_EXTENSIONS:
        raise FileRejected(UNSUPPORTED)

    declared = (declared_type or "").split(";")[0].strip().lower()
    if declared not in DECLARED_TYPES[extension]:
        raise FileRejected(
            "This file's type doesn't match its name. Upload the original PDF or Word document."
        )

    if extension == ".pdf":
        _check_pdf(data)
        return DetectedFile(PDF, "pdf")
    _check_docx(data)
    return DetectedFile(DOCX, "docx")


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
