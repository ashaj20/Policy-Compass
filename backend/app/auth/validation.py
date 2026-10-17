"""Email and password rules, shared by signup and password reset.

Messages are shown to users as-is, so they are plain English.
"""

from email_validator import EmailNotValidError, validate_email

PASSWORD_MIN_LENGTH = 10
PASSWORD_MAX_LENGTH = 128


def normalise_email(value: str) -> str:
    value = (value or "").strip()
    if not value:
        raise ValueError("Enter your email address")
    try:
        result = validate_email(value, check_deliverability=False)
    except EmailNotValidError:
        raise ValueError("Enter a valid email address, like name@organisation.org") from None
    return result.normalized.lower()


def check_password(password: str, email: str | None = None) -> str:
    if not password:
        raise ValueError("Enter a password")
    if len(password) < PASSWORD_MIN_LENGTH:
        raise ValueError(f"Use at least {PASSWORD_MIN_LENGTH} characters")
    if len(password) > PASSWORD_MAX_LENGTH:
        raise ValueError(f"Use no more than {PASSWORD_MAX_LENGTH} characters")
    if not password.strip():
        raise ValueError("Your password can't be only spaces")
    if email and password.strip().lower() == email.strip().lower():
        raise ValueError("Your password can't be your email address")
    return password
