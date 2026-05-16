"""Tests for SendGrid-based mailer."""
from unittest.mock import MagicMock, patch

import pytest

from teebot.mailer import Mailer, OutgoingEmail


@pytest.fixture
def mailer():
    return Mailer(
        api_key="SG.test-key",
        from_email="teebotcarl@gmail.com",
        from_name="Carl's Tee Bot",
    )


def test_send_returns_message_id(mailer):
    with patch("teebot.mailer.httpx.post") as mock_post:
        mock_post.return_value = MagicMock(status_code=202, text="")
        msg_id = mailer.send(OutgoingEmail(
            to="cpfiffner62@gmail.com",
            subject="Test",
            body="Hello",
        ))
        assert msg_id.startswith("<") and msg_id.endswith(">")
        mock_post.assert_called_once()
        call = mock_post.call_args
        assert call.kwargs["headers"]["Authorization"] == "Bearer SG.test-key"
        payload = call.kwargs["json"]
        assert payload["personalizations"][0]["to"][0]["email"] == "cpfiffner62@gmail.com"
        assert payload["from"]["email"] == "teebotcarl@gmail.com"
        assert payload["from"]["name"] == "Carl's Tee Bot"
        assert payload["subject"] == "Test"


def test_send_sets_in_reply_to(mailer):
    with patch("teebot.mailer.httpx.post") as mock_post:
        mock_post.return_value = MagicMock(status_code=202, text="")
        mailer.send(OutgoingEmail(
            to="cpfiffner62@gmail.com",
            subject="Re: test",
            body="reply",
            in_reply_to="<orig@gmail.com>",
        ))
        headers = mock_post.call_args.kwargs["json"]["personalizations"][0]["headers"]
        assert headers["In-Reply-To"] == "<orig@gmail.com>"
        assert headers["References"] == "<orig@gmail.com>"


def test_send_raises_on_non_2xx(mailer):
    with patch("teebot.mailer.httpx.post") as mock_post:
        mock_post.return_value = MagicMock(status_code=401, text="Unauthorized")
        with pytest.raises(RuntimeError, match="401"):
            mailer.send(OutgoingEmail(
                to="cpfiffner62@gmail.com",
                subject="Test",
                body="Hello",
            ))
