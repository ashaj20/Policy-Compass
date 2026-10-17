"""Outgoing email.

With SMTP configured, mail is sent through it. Otherwise (development) each email is written
to the server log so links can be opened from the terminal. Tests swap in MemoryEmailSender.
"""

import logging
import smtplib
from dataclasses import dataclass
from email.message import EmailMessage
from functools import lru_cache
from typing import Protocol

from app.config import Settings, get_settings

logger = logging.getLogger("policy_compass.email")


@dataclass
class Email:
    to: str
    subject: str
    body: str


class EmailSender(Protocol):
    def send(self, email: Email) -> None: ...


class ConsoleEmailSender:
    def send(self, email: Email) -> None:
        logger.info(
            "\n----- EMAIL (not sent: no SMTP configured) -----\nTo: %s\nSubject: %s\n\n%s\n"
            "-----------------------------------------------",
            email.to,
            email.subject,
            email.body,
        )


class SmtpEmailSender:
    def __init__(self, settings: Settings):
        self.settings = settings

    def send(self, email: Email) -> None:
        s = self.settings
        msg = EmailMessage()
        msg["From"] = s.email_from
        msg["To"] = email.to
        msg["Subject"] = email.subject
        msg.set_content(email.body)
        with smtplib.SMTP(s.smtp_host, s.smtp_port, timeout=15) as smtp:
            if s.smtp_starttls:
                smtp.starttls()
            if s.smtp_username:
                smtp.login(s.smtp_username, s.smtp_password or "")
            smtp.send_message(msg)


class MemoryEmailSender:
    def __init__(self) -> None:
        self.outbox: list[Email] = []

    def send(self, email: Email) -> None:
        self.outbox.append(email)


@lru_cache
def get_email_sender() -> EmailSender:
    settings = get_settings()
    return SmtpEmailSender(settings) if settings.smtp_host else ConsoleEmailSender()
