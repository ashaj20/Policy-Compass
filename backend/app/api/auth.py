"""Authentication endpoints (US-001).

Sessions use an httpOnly, SameSite=Lax cookie, so the token is never readable by page
scripts and isn't sent on cross-site form posts.
"""

from fastapi import APIRouter, Response, status
from pydantic import BaseModel, ValidationInfo, field_validator

from app.auth import service
from app.auth.validation import check_password, normalise_email
from app.deps import SESSION_COOKIE, AppSettings, CurrentUser, DbSession, Mailer, SessionToken
from app.organisations.service import memberships_for

router = APIRouter(prefix="/auth", tags=["auth"])

PASSWORDS_DONT_MATCH = "The passwords don't match"


class EmailIn(BaseModel):
    email: str

    @field_validator("email")
    @classmethod
    def valid_email(cls, v: str) -> str:
        return normalise_email(v)


def _confirm_matches(v: str, info: ValidationInfo) -> str:
    # Only compare once the password itself is valid, so one problem is reported at a time.
    if "password" in info.data and v != info.data["password"]:
        raise ValueError(PASSWORDS_DONT_MATCH)
    return v


class SignupIn(EmailIn):
    password: str
    confirm_password: str

    @field_validator("password")
    @classmethod
    def strong_password(cls, v: str, info: ValidationInfo) -> str:
        return check_password(v, info.data.get("email"))

    _confirm = field_validator("confirm_password")(_confirm_matches)


class LoginIn(EmailIn):
    password: str


class TokenIn(BaseModel):
    token: str


class ResetPasswordIn(TokenIn):
    password: str
    confirm_password: str

    @field_validator("password")
    @classmethod
    def strong_password(cls, v: str) -> str:
        return check_password(v)

    _confirm = field_validator("confirm_password")(_confirm_matches)


class MessageOut(BaseModel):
    message: str


class MembershipOut(BaseModel):
    organisation_id: str
    organisation_name: str
    organisation_slug: str
    role: str


class UserOut(BaseModel):
    id: str
    email: str
    # Organisation access comes only from memberships; a new user has none.
    memberships: list[MembershipOut]


def user_out(db, user) -> UserOut:
    return UserOut(
        id=str(user.id),
        email=user.email,
        memberships=[
            MembershipOut(
                organisation_id=str(m.organisation_id),
                organisation_name=m.organisation.name,
                organisation_slug=m.organisation.slug,
                role=m.role,
            )
            for m in memberships_for(db, user)
        ],
    )


@router.post("/signup", status_code=status.HTTP_201_CREATED)
def signup(body: SignupIn, db: DbSession, settings: AppSettings, mailer: Mailer) -> MessageOut:
    service.signup(db, body.email, body.password, settings, mailer)
    return MessageOut(message="Check your email for a link to verify your account.")


@router.post("/verify-email")
def verify_email(body: TokenIn, db: DbSession) -> MessageOut:
    service.verify_email(db, body.token)
    return MessageOut(message="Your email address is verified. You can now sign in.")


@router.post("/resend-verification", status_code=status.HTTP_202_ACCEPTED)
def resend_verification(
    body: EmailIn, db: DbSession, settings: AppSettings, mailer: Mailer
) -> MessageOut:
    service.resend_verification(db, body.email, settings, mailer)
    return MessageOut(
        message="If that account still needs verifying, we've sent a new link to its email address."
    )


@router.post("/login")
def login(body: LoginIn, response: Response, db: DbSession, settings: AppSettings) -> UserOut:
    signed_in = service.login(db, body.email, body.password, settings)
    set_session_cookie(response, signed_in.session_token, settings)
    return user_out(db, signed_in.user)


def set_session_cookie(response: Response, token: str, settings) -> None:
    response.set_cookie(
        SESSION_COOKIE,
        token,
        max_age=settings.session_days * 24 * 3600,
        httponly=True,
        secure=settings.secure_cookies,
        samesite="lax",
        path="/",
    )


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(response: Response, db: DbSession, settings: AppSettings, token: SessionToken = None):
    service.logout(db, token)
    response.delete_cookie(
        SESSION_COOKIE, path="/", httponly=True, secure=settings.secure_cookies, samesite="lax"
    )


@router.get("/me")
def me(user: CurrentUser, db: DbSession) -> UserOut:
    return user_out(db, user)


@router.post("/password-reset/request", status_code=status.HTTP_202_ACCEPTED)
def request_password_reset(
    body: EmailIn, db: DbSession, settings: AppSettings, mailer: Mailer
) -> MessageOut:
    service.request_password_reset(db, body.email, settings, mailer)
    return MessageOut(
        message="If an account exists for that email, we've sent a link to reset the password."
    )


@router.post("/password-reset/confirm")
def confirm_password_reset(body: ResetPasswordIn, db: DbSession) -> MessageOut:
    service.reset_password(db, body.token, body.password)
    return MessageOut(message="Your password has been changed. Please sign in.")
