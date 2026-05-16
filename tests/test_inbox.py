"""Tests for IMAP receiver."""
from unittest.mock import MagicMock, patch

import pytest

from teebot.inbox import Inbox, RawMessage


def test_fetch_unread_returns_messages():
    raw_bytes = b"From: x@y.com\r\nSubject: test\r\n\r\nbody"
    with patch("imaplib.IMAP4_SSL") as imap_cls:
        imap = MagicMock()
        imap_cls.return_value = imap
        imap.login.return_value = ("OK", [b""])
        imap.select.return_value = ("OK", [b"1"])
        imap.search.return_value = ("OK", [b"1 2"])
        imap.fetch.side_effect = [
            ("OK", [(b"1 (RFC822 {N}", raw_bytes), b")"]),
            ("OK", [(b"2 (RFC822 {N}", raw_bytes), b")"]),
        ]
        inbox = Inbox(
            host="imap.gmail.com",
            username="teebotcarl@gmail.com",
            app_password="appsecret",
            sender_allowlist={"x@y.com"},
        )
        messages = inbox.fetch_unread()
        assert len(messages) == 2
        assert all(isinstance(m, RawMessage) for m in messages)
        assert messages[0].uid == "1"
        assert messages[0].raw == raw_bytes


def test_fetch_filters_by_sender_allowlist():
    foreign = b"From: stranger@bad.com\r\nSubject: spam\r\n\r\nbody"
    legit = b"From: x@y.com\r\nSubject: ok\r\n\r\nbody"
    with patch("imaplib.IMAP4_SSL") as imap_cls:
        imap = MagicMock()
        imap_cls.return_value = imap
        imap.login.return_value = ("OK", [b""])
        imap.select.return_value = ("OK", [b"1"])
        imap.search.return_value = ("OK", [b"10 20"])
        imap.fetch.side_effect = [
            ("OK", [(b"10 (RFC822 {N}", foreign), b")"]),
            ("OK", [(b"20 (RFC822 {N}", legit), b")"]),
        ]
        inbox = Inbox(
            host="imap.gmail.com",
            username="teebotcarl@gmail.com",
            app_password="appsecret",
            sender_allowlist={"x@y.com"},
        )
        messages = inbox.fetch_unread()
        assert len(messages) == 1
        assert messages[0].uid == "20"


def test_mark_seen_called():
    raw = b"From: x@y.com\r\nSubject: t\r\n\r\nb"
    with patch("imaplib.IMAP4_SSL") as imap_cls:
        imap = MagicMock()
        imap_cls.return_value = imap
        imap.login.return_value = ("OK", [b""])
        imap.select.return_value = ("OK", [b"1"])
        imap.search.return_value = ("OK", [b"5"])
        imap.fetch.return_value = ("OK", [(b"5 (RFC822 {N}", raw), b")"])
        inbox = Inbox("imap.gmail.com", "u", "p", {"x@y.com"})
        msgs = inbox.fetch_unread()
        inbox.mark_seen(msgs[0].uid)
        imap.store.assert_called_with(b"5", "+FLAGS", "\\Seen")
