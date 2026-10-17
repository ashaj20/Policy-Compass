"""Shared FastAPI dependencies, as Annotated aliases for use in route signatures."""

import uuid
from typing import Annotated

from fastapi import Cookie, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.service import user_for_session
from app.config import Settings, get_settings
from app.db import get_db
from app.email import EmailSender, get_email_sender
from app.errors import AppError, NotFound, PermissionDenied
from app.models import Membership, Role, User
from app.processing import ProcessingRunner, get_runner
from app.storage import Storage, get_storage

SESSION_COOKIE = "pc_session"

DbSession = Annotated[Session, Depends(get_db)]
AppSettings = Annotated[Settings, Depends(get_settings)]
Mailer = Annotated[EmailSender, Depends(get_email_sender)]
SessionToken = Annotated[str | None, Cookie(alias=SESSION_COOKIE)]


def get_current_user(db: DbSession, token: SessionToken = None) -> User:
    user = user_for_session(db, token)
    if user is None:
        raise AppError(401, "not_authenticated", "Please sign in to continue.")
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]
FileStorage = Annotated[Storage, Depends(get_storage)]
Runner = Annotated[ProcessingRunner, Depends(get_runner)]


def get_membership(organisation_id: uuid.UUID, db: DbSession, user: CurrentUser) -> Membership:
    """The signed-in user's membership of the organisation in the URL.

    Non-members get the same 404 as a missing organisation, so other tenants' IDs can't be
    probed (AC-11).
    """
    membership = db.scalar(
        select(Membership).where(
            Membership.organisation_id == organisation_id, Membership.user_id == user.id
        )
    )
    if membership is None:
        raise NotFound("This organisation could not be found.")
    return membership


def require_admin(membership: Annotated[Membership, Depends(get_membership)]) -> Membership:
    if membership.role != Role.ADMIN:
        raise PermissionDenied("Only administrators can do this.")
    return membership


MemberOf = Annotated[Membership, Depends(get_membership)]
AdminOf = Annotated[Membership, Depends(require_admin)]
