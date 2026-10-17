"""Account rules: signup, email verification, sign-in sessions and password reset."""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from urllib.parse import quote

from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

from app.auth.security import hash_password, hash_token, new_token, verify_password
from app.config import Settings
from app.email import Email, EmailSender
from app.errors import AppError
from app.models import AuthToken, User, UserSession

VERIFY_EMAIL = "verify_email"
RESET_PASSWORD = "reset_password"

INVALID_LINK = "This link is invalid or has expired. Please request a new one."


def _now() -> datetime:
    return datetime.now(UTC)


def _get_user_by_email(db: Session, email: str) -> User | None:
    return db.scalar(select(User).where(User.email == email))


def _issue_token(db: Session, user: User, purpose: str, lifetime: timedelta) -> str:
    # Only the newest link of each kind works.
    db.execute(
        update(AuthToken)
        .where(
            AuthToken.user_id == user.id, AuthToken.purpose == purpose, AuthToken.used_at.is_(None)
        )
        .values(used_at=_now())
    )
    token = new_token()
    db.add(
        AuthToken(
            user_id=user.id,
            purpose=purpose,
            token_hash=hash_token(token),
            expires_at=_now() + lifetime,
        )
    )
    return token


def _consume_token(db: Session, token: str, purpose: str) -> User:
    record = db.scalar(
        select(AuthToken)
        .where(AuthToken.token_hash == hash_token(token or ""), AuthToken.purpose == purpose)
        .with_for_update()
    )
    if record is None or record.used_at is not None or record.expires_at <= _now():
        raise AppError(400, "invalid_token", INVALID_LINK)
    record.used_at = _now()
    return record.user


def _link(settings: Settings, path: str, token: str) -> str:
    return f"{settings.public_base_url.rstrip('/')}{path}?token={quote(token)}"


def _send_verification(db: Session, user: User, settings: Settings, sender: EmailSender) -> None:
    token = _issue_token(db, user, VERIFY_EMAIL, timedelta(hours=settings.verify_token_hours))
    sender.send(
        Email(
            to=user.email,
            subject="Verify your Policy Compass account",
            body=(
                "Welcome to Policy Compass.\n\n"
                "Please verify your email address by opening this link:\n"
                f"{_link(settings, '/verify-email', token)}\n\n"
                f"The link expires in {settings.verify_token_hours} hours. "
                "If you didn't create an account, you can ignore this email."
            ),
        )
    )


def signup(db: Session, email: str, password: str, settings: Settings, sender: EmailSender) -> None:
    existing = _get_user_by_email(db, email)
    if existing and existing.is_verified:
        raise AppError(
            409,
            "account_exists",
            "An account with this email already exists. Sign in or reset your password.",
            {"email": "An account with this email already exists"},
        )
    if existing:
        # Signed up before but never verified: keep the account, update the password the
        # person has just chosen, and send a fresh link.
        existing.password_hash = hash_password(password)
        user = existing
    else:
        user = User(email=email, password_hash=hash_password(password))
        db.add(user)
        db.flush()
    _send_verification(db, user, settings, sender)
    db.commit()


def resend_verification(db: Session, email: str, settings: Settings, sender: EmailSender) -> None:
    """Always succeeds from the caller's view, so it can't be used to discover accounts."""
    user = _get_user_by_email(db, email)
    if user and not user.is_verified:
        _send_verification(db, user, settings, sender)
        db.commit()


def verify_email(db: Session, token: str) -> None:
    user = _consume_token(db, token, VERIFY_EMAIL)
    if not user.is_verified:
        user.email_verified_at = _now()
    db.commit()


@dataclass
class SignedIn:
    user: User
    session_token: str


def login(db: Session, email: str, password: str, settings: Settings) -> SignedIn:
    user = _get_user_by_email(db, email)
    if not verify_password(user.password_hash if user else None, password):
        raise AppError(401, "invalid_credentials", "The email or password is incorrect.")
    if not user.is_verified:
        raise AppError(
            403,
            "email_not_verified",
            "Please verify your email address before signing in. "
            "Check your inbox, or we can send you a new link.",
        )
    token = new_token()
    db.add(
        UserSession(
            user_id=user.id,
            token_hash=hash_token(token),
            expires_at=_now() + timedelta(days=settings.session_days),
        )
    )
    db.commit()
    return SignedIn(user=user, session_token=token)


def user_for_session(db: Session, token: str | None) -> User | None:
    if not token:
        return None
    session = db.scalar(
        select(UserSession).where(
            UserSession.token_hash == hash_token(token), UserSession.expires_at > _now()
        )
    )
    return session.user if session else None


def logout(db: Session, token: str | None) -> None:
    if token:
        db.execute(delete(UserSession).where(UserSession.token_hash == hash_token(token)))
        db.commit()


def request_password_reset(
    db: Session, email: str, settings: Settings, sender: EmailSender
) -> None:
    """Always succeeds from the caller's view, so it can't be used to discover accounts."""
    user = _get_user_by_email(db, email)
    if user is None:
        return
    token = _issue_token(db, user, RESET_PASSWORD, timedelta(minutes=settings.reset_token_minutes))
    sender.send(
        Email(
            to=user.email,
            subject="Reset your Policy Compass password",
            body=(
                "We received a request to reset your Policy Compass password.\n\n"
                "Choose a new password by opening this link:\n"
                f"{_link(settings, '/reset-password', token)}\n\n"
                f"The link expires in {settings.reset_token_minutes} minutes. "
                "If you didn't ask for this, you can ignore this email; your password "
                "won't change."
            ),
        )
    )
    db.commit()


def reset_password(db: Session, token: str, new_password: str) -> None:
    user = _consume_token(db, token, RESET_PASSWORD)
    user.password_hash = hash_password(new_password)
    # Opening the emailed link proves control of the inbox.
    if not user.is_verified:
        user.email_verified_at = _now()
    # Sign out everywhere, in case the old password was compromised.
    db.execute(delete(UserSession).where(UserSession.user_id == user.id))
    db.commit()
