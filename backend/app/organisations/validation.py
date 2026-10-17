"""Organisation field rules. Messages are shown to users as-is."""

import re
from urllib.parse import urlparse

SLUG_MIN = 3
SLUG_MAX = 50
SLUG_PATTERN = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")

# Words that would clash with app routes or could mislead visitors.
RESERVED_SLUGS = frozenset(
    {
        "admin", "api", "app", "assets", "auth", "help", "internal", "login", "logout", "p",
        "policy-compass", "policycompass", "public", "settings", "signup", "static", "support",
        "www",
    }
)  # fmt: skip


def check_name(value: str) -> str:
    value = " ".join((value or "").split())
    if not value:
        raise ValueError("Enter your organisation's name")
    if len(value) < 2:
        raise ValueError("Use at least 2 characters")
    if len(value) > 100:
        raise ValueError("Use no more than 100 characters")
    return value


def check_slug(value: str) -> str:
    value = (value or "").strip()
    if not value:
        raise ValueError("Enter a public URL")
    if value != value.lower():
        raise ValueError("Use lowercase letters only")
    if len(value) < SLUG_MIN:
        raise ValueError(f"Use at least {SLUG_MIN} characters")
    if len(value) > SLUG_MAX:
        raise ValueError(f"Use no more than {SLUG_MAX} characters")
    if not SLUG_PATTERN.match(value):
        raise ValueError(
            "Use only lowercase letters, numbers and single hyphens, "
            "with no spaces and no hyphen at the start or end"
        )
    if value in RESERVED_SLUGS:
        raise ValueError("This URL is reserved. Please choose another")
    return value


def check_website(value: str | None) -> str | None:
    value = (value or "").strip()
    if not value:
        return None
    if "://" not in value:
        value = "https://" + value
    parsed = urlparse(value)
    host = parsed.hostname or ""
    if parsed.scheme not in ("http", "https") or "." not in host or " " in value:
        raise ValueError("Enter a valid website address, like https://www.organisation.org")
    if len(value) > 300:
        raise ValueError("Use no more than 300 characters")
    return value


# Logos: raster formats only. SVG is refused because it can carry scripts.
_LOGO_SIGNATURES = {
    "image/png": (b"\x89PNG\r\n\x1a\n", "png"),
    "image/jpeg": (b"\xff\xd8\xff", "jpg"),
}


def detect_logo_type(data: bytes) -> tuple[str, str] | None:
    """Return (content type, extension) from the file's actual bytes, not its name."""
    for content_type, (signature, extension) in _LOGO_SIGNATURES.items():
        if data.startswith(signature):
            return content_type, extension
    if len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp", "webp"
    return None
