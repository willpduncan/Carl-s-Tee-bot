"""SMTP sender for outbound emails."""
from __future__ import annotations

import smtplib
import ssl
import uuid
from dataclasses import dataclass
from email.message import EmailMessage


@dataclass(frozen=True)
class OutgoingEmail:
    to: str
    subject: str
    body: str
    in_reply_to: str | None = None
    from_address: str | None = None  # defaults to Mailer's username


class Mailer:
    """Sends mail via Gmail SMTP.

    Uses SSL on port 465 by default (more reliable across cloud hosts that
    may block port 587). Pass smtp_port=587 to use STARTTLS instead.
    """

    def __init__(self, smtp_host: str, smtp_port: int, username: str, app_password: str):
        self._host = smtp_host
        self._port = smtp_port
        self._user = username
        self._pw = app_password

    def send(self, email: OutgoingEmail) -> str:
        msg = EmailMessage()
        msg_id = f"<{uuid.uuid4()}@teebot.local>"
        msg["Message-ID"] = msg_id
        msg["From"] = email.from_address or self._user
        msg["To"] = email.to
        msg["Subject"] = email.subject
        if email.in_reply_to:
            msg["In-Reply-To"] = email.in_reply_to
            msg["References"] = email.in_reply_to
        msg.set_content(email.body)

        if self._port == 465:
            with smtplib.SMTP_SSL(self._host, self._port,
                                  context=ssl.create_default_context()) as smtp:
                smtp.login(self._user, self._pw)
                smtp.send_message(msg)
        else:
            with smtplib.SMTP(self._host, self._port) as smtp:
                smtp.starttls()
                smtp.login(self._user, self._pw)
                smtp.send_message(msg)
        return msg_id
