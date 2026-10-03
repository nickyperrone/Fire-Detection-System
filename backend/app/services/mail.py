"""Sending email over SMTP (docs/09-accounts-and-alerts.md#sending)."""

import smtplib
from collections.abc import Callable
from email.message import EmailMessage

from app.config import Settings

SendEmail = Callable[[EmailMessage], None]

# Errors that mean "not sent, try again later", as opposed to a bug.
SEND_ERRORS = (smtplib.SMTPException, OSError)


def message(settings: Settings, to: str, subject: str, body: str) -> EmailMessage:
    email = EmailMessage()
    email["From"] = settings.smtp_from
    email["To"] = to
    email["Subject"] = subject
    email.set_content(body)
    return email


def smtp_sender(settings: Settings) -> SendEmail:
    def send(email: EmailMessage) -> None:
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=20) as smtp:
            if settings.smtp_starttls:
                smtp.starttls()
            if settings.smtp_username:
                smtp.login(settings.smtp_username, settings.smtp_password)
            smtp.send_message(email)

    return send
