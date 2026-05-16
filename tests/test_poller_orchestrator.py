"""Tests for the poller orchestrator."""
from datetime import date, datetime
from unittest.mock import MagicMock

import pytest

from teebot.db import connect, init_schema
from teebot.inbox import RawMessage
from teebot.poller_orchestrator import PollerOrchestrator


@pytest.fixture
def db(tmp_path):
    c = connect(str(tmp_path / "t.db"))
    init_schema(c)
    yield c
    c.close()


def _email_bytes(*, frm: str, body: str, subject: str = "tee time", in_reply_to: str | None = None) -> bytes:
    headers = f"From: {frm}\r\nTo: bot@teebot.local\r\nSubject: {subject}\r\n"
    if in_reply_to:
        headers += f"In-Reply-To: {in_reply_to}\r\n"
    headers += "\r\n"
    return (headers + body).encode()


def test_processes_new_request(db):
    inbox = MagicMock()
    mailer = MagicMock()
    mailer.send.return_value = "<sent-1@teebot.local>"
    inbox.fetch_unread.return_value = [
        RawMessage(
            uid="1",
            raw=_email_bytes(
                frm="cpfiffner62@gmail.com",
                body="Day: Sunday May 24\nCourse: Green\nWindow: 8 to 10 AM\nPreferred: 9:00 AM\n",
            ),
            sender="cpfiffner62@gmail.com",
        )
    ]
    orch = PollerOrchestrator(
        db=db, inbox=inbox, mailer=mailer,
        bot_email="teebotcarl@gmail.com", carl_email="cpfiffner62@gmail.com",
        today=date(2026, 5, 15),
    )
    orch.run_once()
    rows = list(db.execute("SELECT * FROM requests WHERE status='pending'"))
    assert len(rows) == 1
    assert rows[0]["target_date"] == "2026-05-24"
    inbox.mark_seen.assert_called_with("1")
    mailer.send.assert_called_once()
    sent = mailer.send.call_args[0][0]
    assert "Got it" in sent.body
    assert "Sunday" in sent.body


def test_processes_cancel(db):
    # Pre-insert a pending request
    db.execute("""
        INSERT INTO requests (target_date, course, preferred_time,
            window_start, window_end, status, created_at, updated_at)
        VALUES ('2026-05-24', 'Green', '09:00', '08:00', '10:00',
            'pending', '2026-05-15 12:00', '2026-05-15 12:00')
    """)
    inbox = MagicMock()
    mailer = MagicMock()
    mailer.send.return_value = "<sent-2@teebot.local>"
    inbox.fetch_unread.return_value = [
        RawMessage(
            uid="2",
            raw=_email_bytes(frm="cpfiffner62@gmail.com", subject="Re: tee time", body="cancel"),
            sender="cpfiffner62@gmail.com",
        )
    ]
    orch = PollerOrchestrator(
        db=db, inbox=inbox, mailer=mailer,
        bot_email="teebotcarl@gmail.com", carl_email="cpfiffner62@gmail.com",
        today=date(2026, 5, 15),
    )
    orch.run_once()
    rows = list(db.execute("SELECT status FROM requests"))
    assert all(r["status"] == "cancelled" for r in rows)


def test_replies_with_format_help_on_malformed(db):
    inbox = MagicMock()
    mailer = MagicMock()
    mailer.send.return_value = "<sent-3@teebot.local>"
    inbox.fetch_unread.return_value = [
        RawMessage(
            uid="3",
            raw=_email_bytes(frm="cpfiffner62@gmail.com", body="hi can I tee?"),
            sender="cpfiffner62@gmail.com",
        )
    ]
    orch = PollerOrchestrator(
        db=db, inbox=inbox, mailer=mailer,
        bot_email="teebotcarl@gmail.com", carl_email="cpfiffner62@gmail.com",
        today=date(2026, 5, 15),
    )
    orch.run_once()
    sent = mailer.send.call_args[0][0]
    assert "couldn't understand" in sent.body.lower() or "format" in sent.body.lower()


def test_handles_partner_reply(db):
    # Pre-insert a booking with a known confirmation_message_id
    db.execute("""
        INSERT INTO requests (id, target_date, course, preferred_time,
            window_start, window_end, status, created_at, updated_at)
        VALUES (1, '2026-05-24', 'Green', '09:00', '08:00', '10:00',
            'succeeded', '2026-05-15 12:00', '2026-05-15 12:00')
    """)
    db.execute("""
        INSERT INTO bookings (id, request_id, target_date, booked_time, course,
            partner_status, confirmation_message_id, created_at)
        VALUES (1, 1, '2026-05-24', '09:00', 'Green', 'pending_choice',
            '<conf-1@teebot.local>', '2026-05-15 12:01')
    """)
    inbox = MagicMock()
    mailer = MagicMock()
    mailer.send.return_value = "<sent-4@teebot.local>"
    inbox.fetch_unread.return_value = [
        RawMessage(
            uid="4",
            raw=_email_bytes(
                frm="cpfiffner62@gmail.com",
                subject="Re: ✓ Booked",
                body="names: Bob Smith, Tom Jones, Jim Davis",
                in_reply_to="<conf-1@teebot.local>",
            ),
            sender="cpfiffner62@gmail.com",
        )
    ]
    orch = PollerOrchestrator(
        db=db, inbox=inbox, mailer=mailer,
        bot_email="teebotcarl@gmail.com", carl_email="cpfiffner62@gmail.com",
        today=date(2026, 5, 15),
    )
    orch.run_once()
    row = db.execute("SELECT partner_status, partner_names FROM bookings WHERE id=1").fetchone()
    assert row["partner_status"] == "names_provided"
    import json
    assert json.loads(row["partner_names"]) == ["Bob Smith", "Tom Jones", "Jim Davis"]
