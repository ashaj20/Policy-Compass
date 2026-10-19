"""Recording analytics events (US-035).

`track()` adds an event to the caller's session, so it is saved (or rolled back) together with
the change it describes. Only non-personal properties may be passed: never question text, user
identifiers or network addresses.
"""

import uuid

from sqlalchemy.orm import Session

from app.models import AnalyticsEvent, AnalyticsEventType

ALLOWED_PROPERTIES = {"audience", "reason", "helpful", "policy_id", "version_id", "from_cache"}


def track(db: Session, organisation_id: uuid.UUID, event: AnalyticsEventType, **properties) -> None:
    unexpected = set(properties) - ALLOWED_PROPERTIES
    if unexpected:
        raise ValueError(f"Analytics properties not allowed: {sorted(unexpected)}")
    db.add(
        AnalyticsEvent(
            organisation_id=organisation_id,
            event=event,
            properties={
                k: (str(v) if isinstance(v, uuid.UUID) else v) for k, v in properties.items()
            },
        )
    )
