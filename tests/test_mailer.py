"""Tests for SMTP sender."""
from unittest.mock import MagicMock, patch

import pytest

from teebot.mailer import Mailer, OutgoingEmail


@pytest.fixture
def mailer():
    return Mailer(
        smtp_host="smtp.gmail.com",
        smtp_port=587,
        username="teebotcarl@gmail.com",
        app_password="appspecificpassword",
    )


def test_send_returns_message_id(mailer):
    with patch("smtplib.SMTP") as smtp_cls:
        smtp = MagicMock()
        smtp_cls.return_value.__enter__.return_value = smtp
        msg_id = mailer.send(OutgoingEmail(
            to="cpfiffner62@gmail.com",
            subject="Test",
            body="Hello",
        ))
        assert msg_id.startswith("<") and msg_id.endswith(">")
        smtp.starttls.assert_called_once()
        smtp.login.assert_called_once_with("teebotcarl@gmail.com", "appspecificpassword")
        smtp.send_message.assert_called_once()


def test_send_sets_in_reply_to(mailer):
    with patch("smtplib.SMTP") as smtp_cls:
        smtp = MagicMock()
        smtp_cls.return_value.__enter__.return_value = smtp
        mailer.send(OutgoingEmail(
            to="cpfiffner62@gmail.com",
            subject="Re: test",
            body="reply",
            in_reply_to="<orig@gmail.com>",
        ))
        sent = smtp.send_message.call_args[0][0]
        assert sent["In-Reply-To"] == "<orig@gmail.com>"
        assert "<orig@gmail.com>" in sent["References"]
