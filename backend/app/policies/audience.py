"""The audience rule (US-007): which policies a requester may ever see.

This is the single definition of the public/internal boundary (AC-03, AC-12). Every query that
reads policy content for a requester — retrieval, citations, public endpoints — must filter with
`audience_filter()` rather than re-deriving the rule.
"""

from enum import StrEnum

from sqlalchemy import ColumnElement

from app.models import Audience, Policy


class Requester(StrEnum):
    """Who is asking: the public page and widget, or signed-in members of the organisation."""

    PUBLIC = "PUBLIC"
    INTERNAL = "INTERNAL"


PERMITTED: dict[Requester, frozenset[Audience]] = {
    # Public users never see internal-only content.
    Requester.PUBLIC: frozenset({Audience.PUBLIC, Audience.BOTH}),
    # Staff may see everything approved for any audience (no per-policy restriction in beta).
    Requester.INTERNAL: frozenset({Audience.INTERNAL, Audience.PUBLIC, Audience.BOTH}),
}


def permitted_audiences(requester: Requester) -> frozenset[Audience]:
    return PERMITTED[requester]


def is_visible_to(audience: str, requester: Requester) -> bool:
    return Audience(audience) in PERMITTED[requester]


def audience_filter(requester: Requester) -> ColumnElement[bool]:
    """SQL condition limiting policies to those the requester may see."""
    return Policy.audience.in_([str(a) for a in PERMITTED[requester]])
