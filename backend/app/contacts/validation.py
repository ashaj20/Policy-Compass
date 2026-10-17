"""Contact field rules (US-024). Messages are shown to users as-is."""

import re

from app.auth.validation import normalise_email
from app.models import RouteType
from app.organisations.validation import check_website

PHONE = re.compile(r"^\+?[0-9 ()\-]{6,25}$")


def check_text(value: str | None, label: str, max_len: int, required: bool) -> str | None:
    value = " ".join((value or "").split())
    if not value:
        if required:
            raise ValueError(f"Enter {label}")
        return None
    if len(value) > max_len:
        raise ValueError(f"Use no more than {max_len} characters")
    return value


def check_email(value: str | None) -> str | None:
    value = (value or "").strip()
    if not value:
        return None
    return normalise_email(value)


def check_phone(value: str | None) -> str | None:
    value = " ".join((value or "").split())
    if not value:
        return None
    if not PHONE.match(value) or sum(c.isdigit() for c in value) < 6:
        raise ValueError("Enter a valid phone number, like 0300 123 4567")
    return value


def check_destination(route_type: RouteType, value: str) -> str:
    """Validate the destination against the route type: email, phone or web address."""
    value = (value or "").strip()
    if route_type == RouteType.EMAIL:
        if not value:
            raise ValueError("Enter the email address")
        return normalise_email(value)
    if route_type == RouteType.PHONE:
        if not value:
            raise ValueError("Enter the phone number")
        phone = check_phone(value)
        assert phone is not None
        return phone
    if not value:
        raise ValueError("Enter the web address")
    url = check_website(value)
    if url is None:
        raise ValueError("Enter the web address")
    return url
