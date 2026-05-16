"""HTTP-based email sender via the SendGrid API.

Railway (and many other PaaS providers) block outbound SMTP on
ports 25/465/587, so we use SendGrid's HTTPS API (port 443) instead.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass

import httpx


SENDGRID_API_URL = "https://api.sendgrid.com/v3/mail/send"


@dataclass(frozen=True)
class OutgoingEmail:
    to: str
    subject: str
    body: str
    in_reply_to: str | None = None
    from_address: str | None = None  # defaults to Mailer's verified sender


class Mailer:
    """Sends transactional email via SendGrid HTTP API."""

    def __init__(self, api_key: str, from_email: str, from_name: str = ""):
        self._key = api_key
        self._from_email = from_email
        self._from_name = from_name

    def send(self, email: OutgoingEmail) -> str:
        """Send an email. Returns the generated Message-ID for threading.

        Raises RuntimeError on non-2xx response from SendGrid.
        """
        msg_id = f"<{uuid.uuid4()}@teebot.local>"
        sender = email.from_address or self._from_email
        from_block: dict[str, str] = {"email": sender}
        if self._from_name:
            from_block["name"] = self._from_name

        headers: dict[str, str] = {"Message-ID": msg_id}
        if email.in_reply_to:
            headers["In-Reply-To"] = email.in_reply_to
            headers["References"] = email.in_reply_to

        payload = {
            "personalizations": [{
                "to": [{"email": email.to}],
                "headers": headers,
            }],
            "from": from_block,
            "subject": email.subject,
            "content": [{"type": "text/plain", "value": email.body}],
        }

        response = httpx.post(
            SENDGRID_API_URL,
            headers={
                "Authorization": f"Bearer {self._key}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=30.0,
        )
        if response.status_code not in (200, 202):
            raise RuntimeError(
                f"SendGrid returned {response.status_code}: {response.text[:200]}"
            )
        return msg_id
