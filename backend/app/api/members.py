"""Membership endpoints (US-003). Managing members is for administrators only."""

import uuid
from datetime import datetime

from fastapi import APIRouter, Response, status
from pydantic import BaseModel, ValidationInfo, field_validator

from app.api.auth import UserOut, set_session_cookie, user_out
from app.auth.validation import check_password, normalise_email
from app.deps import AdminOf, AppSettings, CurrentUser, DbSession, Mailer
from app.models import Invitation, Membership, Role
from app.organisations import members

router = APIRouter(tags=["members"])


class MemberOut(BaseModel):
    id: str
    user_id: str
    email: str
    role: Role
    joined_at: datetime
    is_you: bool


class InvitationOut(BaseModel):
    id: str
    email: str
    role: Role
    invited_at: datetime
    expires_at: datetime
    invited_by: str | None


class MembersOut(BaseModel):
    members: list[MemberOut]
    invitations: list[InvitationOut]


class InviteIn(BaseModel):
    email: str
    role: Role = Role.STAFF

    _email = field_validator("email")(normalise_email)


class RoleIn(BaseModel):
    role: Role


class TokenIn(BaseModel):
    token: str


class AcceptNewIn(TokenIn):
    password: str
    confirm_password: str

    @field_validator("password")
    @classmethod
    def strong_password(cls, v: str) -> str:
        return check_password(v)

    @field_validator("confirm_password")
    @classmethod
    def matches(cls, v: str, info: ValidationInfo) -> str:
        if "password" in info.data and v != info.data["password"]:
            raise ValueError("The passwords don't match")
        return v


class InvitationDetailsOut(BaseModel):
    organisation_name: str
    email: str
    role: Role
    account_exists: bool


def member_out(m: Membership, you) -> MemberOut:
    return MemberOut(
        id=str(m.id),
        user_id=str(m.user_id),
        email=m.user.email,
        role=m.role,
        joined_at=m.created_at,
        is_you=m.user_id == you.id,
    )


def invitation_out(i: Invitation) -> InvitationOut:
    return InvitationOut(
        id=str(i.id),
        email=i.email,
        role=i.role,
        invited_at=i.created_at,
        expires_at=i.expires_at,
        invited_by=i.invited_by.email if i.invited_by else None,
    )


# --- Administrator endpoints, scoped to one organisation ---

ORG = "/organisations/{organisation_id}"


@router.get(f"{ORG}/members")
def list_members(admin: AdminOf, db: DbSession, user: CurrentUser) -> MembersOut:
    org = admin.organisation
    return MembersOut(
        members=[member_out(m, user) for m in members.list_members(db, org)],
        invitations=[invitation_out(i) for i in members.list_open_invitations(db, org)],
    )


@router.post(f"{ORG}/invitations", status_code=status.HTTP_201_CREATED)
def invite(
    body: InviteIn,
    admin: AdminOf,
    db: DbSession,
    user: CurrentUser,
    settings: AppSettings,
    mailer: Mailer,
) -> InvitationOut:
    invitation = members.invite(
        db, admin.organisation, user, body.email, body.role, settings, mailer
    )
    return invitation_out(invitation)


@router.post(f"{ORG}/invitations/{{invitation_id}}/resend")
def resend_invitation(
    invitation_id: uuid.UUID,
    admin: AdminOf,
    db: DbSession,
    user: CurrentUser,
    settings: AppSettings,
    mailer: Mailer,
) -> InvitationOut:
    invitation = members.resend_invitation(
        db, admin.organisation, invitation_id, user, settings, mailer
    )
    return invitation_out(invitation)


@router.delete(f"{ORG}/invitations/{{invitation_id}}", status_code=status.HTTP_204_NO_CONTENT)
def revoke_invitation(invitation_id: uuid.UUID, admin: AdminOf, db: DbSession) -> None:
    members.revoke_invitation(db, admin.organisation, admin.user, invitation_id)


@router.patch(f"{ORG}/members/{{membership_id}}")
def change_role(
    membership_id: uuid.UUID, body: RoleIn, admin: AdminOf, db: DbSession, user: CurrentUser
) -> MemberOut:
    membership = members.change_role(db, admin.organisation, admin.user, membership_id, body.role)
    return member_out(membership, user)


@router.delete(f"{ORG}/members/{{membership_id}}", status_code=status.HTTP_204_NO_CONTENT)
def remove_member(membership_id: uuid.UUID, admin: AdminOf, db: DbSession) -> None:
    members.remove_member(db, admin.organisation, admin.user, membership_id)


# --- Invitee endpoints. The token travels in the body, never the URL path or logs. ---


@router.post("/invitations/lookup")
def lookup_invitation(body: TokenIn, db: DbSession) -> InvitationDetailsOut:
    d = members.describe_invitation(db, body.token)
    return InvitationDetailsOut(
        organisation_name=d.organisation_name,
        email=d.email,
        role=d.role,
        account_exists=d.account_exists,
    )


@router.post("/invitations/accept")
def accept_invitation(body: TokenIn, db: DbSession, user: CurrentUser) -> UserOut:
    members.accept_as_existing_user(db, body.token, user)
    return user_out(db, user)


@router.post("/invitations/accept-new")
def accept_invitation_new_account(
    body: AcceptNewIn, response: Response, db: DbSession, settings: AppSettings
) -> UserOut:
    user, session_token = members.accept_as_new_user(db, body.token, body.password, settings)
    set_session_cookie(response, session_token, settings)
    return user_out(db, user)
