"""Shared FastAPI dependencies, as Annotated aliases for use in route signatures."""

from typing import Annotated

from fastapi import Cookie, Depends
from sqlalchemy.orm import Session

from app.auth.service import user_for_session
from app.config import Settings, get_settings
from app.db import get_db
from app.email import EmailSender, get_email_sender
from app.errors import AppError
from app.models import User

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
