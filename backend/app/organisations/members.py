"""Organisation membership: invitations, roles and removal (US-003).

Administrators invite people by email. Nothing is revealed to an administrator about whether
the invited address already has an account, or belongs to another organisation (AC-11); those
checks happen when the invitee accepts.
"""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from urllib.parse import quote

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.auth.security import hash_password, hash_token, new_token
from app.auth.service import create_session
from app.config import Settings
from app.email import Email, EmailSender
from app.errors import AppError, NotFound
from app.models import Invitation, Membership, Organisation, Role, User

INVALID_INVITATION = (
    "This invitation is invalid or has expired. Ask your administrator to send a new one."
)
LAST_ADMIN = "An organisation must have at least one administrator."
ROLE_LABELS = {Role.ADMIN: "Administrator", Role.STAFF: "Staff member"}


def _now() -> datetime:
    return datetime.now(UTC)


# --- Listing ---


def list_members(db: Session, organisation: Organisation) -> list[Membership]:
    return list(
        db.scalars(
            select(Membership)
            .join(User)
            .where(Membership.organisation_id == organisation.id)
            .order_by(Membership.created_at, User.email)
        )
    )


def list_open_invitations(db: Session, organisation: Organisation) -> list[Invitation]:
    return list(
        db.scalars(
            select(Invitation)
            .where(
                Invitation.organisation_id == organisation.id,
                Invitation.accepted_at.is_(None),
                Invitation.revoked_at.is_(None),
            )
            .order_by(Invitation.created_at)
        )
    )


# --- Inviting ---


def _send_invitation(
    invitation: Invitation, token: str, inviter: User, settings: Settings, sender: EmailSender
) -> None:
    org = invitation.organisation
    link = f"{settings.public_base_url.rstrip('/')}/invite?token={quote(token)}"
    sender.send(
        Email(
            to=invitation.email,
            subject=f"You've been invited to {org.name} on Policy Compass",
            body=(
                f"{inviter.email} has invited you to join {org.name} on Policy Compass as a "
                f"{ROLE_LABELS[Role(invitation.role)].lower()}.\n\n"
                f"Accept the invitation by opening this link:\n{link}\n\n"
                f"The link expires in {settings.invitation_days} days. If you weren't expecting "
                "this, you can ignore this email."
            ),
        )
    )


def invite(
    db: Session,
    organisation: Organisation,
    inviter: User,
    email: str,
    role: Role,
    settings: Settings,
    sender: EmailSender,
) -> Invitation:
    already_member = db.scalar(
        select(Membership.id)
        .join(User)
        .where(Membership.organisation_id == organisation.id, User.email == email)
    )
    if already_member:
        msg = "This person is already a member of your organisation"
        raise AppError(409, "already_member", msg, {"email": msg})

    existing = db.scalar(
        select(Invitation).where(
            Invitation.organisation_id == organisation.id,
            Invitation.email == email,
            Invitation.accepted_at.is_(None),
            Invitation.revoked_at.is_(None),
        )
    )
    if existing and existing.expires_at > _now():
        msg = "An invitation has already been sent to this email address. You can resend it."
        raise AppError(409, "already_invited", msg, {"email": msg})
    if existing:
        existing.revoked_at = _now()  # expired; replace it
        db.flush()

    token = new_token()
    invitation = Invitation(
        organisation=organisation,
        email=email,
        role=role,
        token_hash=hash_token(token),
        invited_by_id=inviter.id,
        expires_at=_now() + timedelta(days=settings.invitation_days),
    )
    db.add(invitation)
    db.flush()
    _send_invitation(invitation, token, inviter, settings, sender)
    db.commit()
    return invitation


def _open_invitation_in(db: Session, organisation: Organisation, invitation_id) -> Invitation:
    invitation = db.get(Invitation, invitation_id)
    if (
        invitation is None
        or invitation.organisation_id != organisation.id
        or not invitation.is_open
    ):
        raise NotFound("This invitation could not be found.")
    return invitation


def resend_invitation(
    db: Session,
    organisation: Organisation,
    invitation_id,
    inviter: User,
    settings: Settings,
    sender: EmailSender,
) -> Invitation:
    invitation = _open_invitation_in(db, organisation, invitation_id)
    token = new_token()  # the previous link stops working
    invitation.token_hash = hash_token(token)
    invitation.expires_at = _now() + timedelta(days=settings.invitation_days)
    _send_invitation(invitation, token, inviter, settings, sender)
    db.commit()
    return invitation


def revoke_invitation(db: Session, organisation: Organisation, invitation_id) -> None:
    invitation = _open_invitation_in(db, organisation, invitation_id)
    invitation.revoked_at = _now()
    db.commit()


# --- Accepting ---


def _valid_invitation(db: Session, token: str) -> Invitation:
    invitation = db.scalar(
        select(Invitation).where(Invitation.token_hash == hash_token(token or "")).with_for_update()
    )
    if invitation is None or not invitation.is_open or invitation.expires_at <= _now():
        raise AppError(400, "invalid_invitation", INVALID_INVITATION)
    return invitation


@dataclass
class InvitationDetails:
    organisation_name: str
    email: str
    role: str
    account_exists: bool


def describe_invitation(db: Session, token: str) -> InvitationDetails:
    """What the invite page needs. Only the holder of the emailed token can see this."""
    invitation = _valid_invitation(db, token)
    account_exists = db.scalar(select(User.id).where(User.email == invitation.email)) is not None
    return InvitationDetails(
        organisation_name=invitation.organisation.name,
        email=invitation.email,
        role=invitation.role,
        account_exists=account_exists,
    )


def _join(db: Session, invitation: Invitation, user: User) -> Membership:
    if db.scalar(select(Membership.id).where(Membership.user_id == user.id)):
        raise AppError(
            409,
            "already_in_organisation",
            "You already belong to an organisation. In the beta, each person can belong to "
            "one organisation.",
        )
    membership = Membership(
        organisation_id=invitation.organisation_id, user_id=user.id, role=invitation.role
    )
    db.add(membership)
    invitation.accepted_at = _now()
    # Opening the emailed link proves the person controls this address.
    if not user.is_verified:
        user.email_verified_at = _now()
    return membership


def accept_as_existing_user(db: Session, token: str, user: User) -> Membership:
    invitation = _valid_invitation(db, token)
    if user.email != invitation.email:
        raise AppError(
            403,
            "wrong_account",
            f"This invitation was sent to {invitation.email}. Sign in with that email address "
            "to accept it.",
        )
    membership = _join(db, invitation, user)
    db.commit()
    return membership


def accept_as_new_user(
    db: Session, token: str, password: str, settings: Settings
) -> tuple[User, str]:
    invitation = _valid_invitation(db, token)
    if db.scalar(select(User.id).where(User.email == invitation.email)):
        raise AppError(
            409,
            "account_exists",
            "An account already exists for this email address. Sign in to accept the invitation.",
        )
    user = User(email=invitation.email, password_hash=hash_password(password))
    db.add(user)
    db.flush()
    _join(db, invitation, user)
    session_token = create_session(db, user, settings)
    db.commit()
    return user, session_token


# --- Roles and removal ---


def _member_in(db: Session, organisation: Organisation, membership_id) -> Membership:
    # Lock the organisation so two admins can't both demote/remove each other at once.
    db.scalar(select(Organisation).where(Organisation.id == organisation.id).with_for_update())
    membership = db.get(Membership, membership_id)
    if membership is None or membership.organisation_id != organisation.id:
        raise NotFound("This member could not be found.")
    return membership


def _admin_count(db: Session, organisation: Organisation) -> int:
    return db.scalar(
        select(func.count())
        .select_from(Membership)
        .where(Membership.organisation_id == organisation.id, Membership.role == Role.ADMIN)
    )


def change_role(db: Session, organisation: Organisation, membership_id, role: Role) -> Membership:
    membership = _member_in(db, organisation, membership_id)
    if membership.role == Role.ADMIN and role != Role.ADMIN and _admin_count(db, organisation) <= 1:
        raise AppError(409, "last_admin", LAST_ADMIN)
    membership.role = role
    db.commit()
    return membership


def remove_member(db: Session, organisation: Organisation, membership_id) -> None:
    membership = _member_in(db, organisation, membership_id)
    if membership.role == Role.ADMIN and _admin_count(db, organisation) <= 1:
        raise AppError(409, "last_admin", LAST_ADMIN)
    db.delete(membership)
    db.commit()
