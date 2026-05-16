"""Tests for the booker orchestrator (5-phase race)."""
from datetime import date, datetime, timedelta
from unittest.mock import MagicMock, patch

import httpx
import pytest

from teebot.booker_orchestrator import (
    BookerOrchestrator,
    BookerOutcome,
    DetectionSignal,
)
from teebot.db import connect, init_schema


@pytest.fixture
def db(tmp_path):
    c = connect(str(tmp_path / "t.db"))
    init_schema(c)
    yield c
    c.close()


def _insert_pending_request(conn, target_date: date):
    conn.execute("""
        INSERT INTO requests (target_date, course, preferred_time,
            window_start, window_end, status, created_at, updated_at)
        VALUES (?, 'Green', '09:00', '08:00', '10:00', 'pending',
            '2026-05-15 12:00', '2026-05-15 12:00')
    """, (target_date.isoformat(),))


def test_preflight_no_request_exits_cleanly(db):
    orch = BookerOrchestrator(
        db=db,
        today=date(2026, 5, 15),
        target_offset_days=5,
        member_id="10326",
        member_name="Carl A Pfiffner",
        member_user="6605",
        foretees_username="x",
        foretees_password="y",
    )
    outcome = orch.run()
    assert outcome.skipped is True
    assert outcome.skipped_reason == "no_pending_request"


def test_preflight_bot_disabled_exits_cleanly(db):
    _insert_pending_request(db, date(2026, 5, 20))
    db.execute("UPDATE config SET bot_enabled = 0")
    orch = BookerOrchestrator(
        db=db,
        today=date(2026, 5, 15),
        target_offset_days=5,
        member_id="10326",
        member_name="Carl A Pfiffner",
        member_user="6605",
        foretees_username="x",
        foretees_password="y",
    )
    outcome = orch.run()
    assert outcome.skipped is True
    assert outcome.skipped_reason == "bot_disabled"


def test_detection_signal_disables_bot(db):
    _insert_pending_request(db, date(2026, 5, 20))
    # Stub all ForeTees calls so they raise DetectionSignal during auth
    with patch("teebot.booker_orchestrator.login") as mock_login:
        mock_login.side_effect = DetectionSignal("datadome cookie set")
        orch = BookerOrchestrator(
            db=db,
            today=date(2026, 5, 15),
            target_offset_days=5,
            member_id="10326",
            member_name="Carl",
            member_user="6605",
            foretees_username="x",
            foretees_password="y",
        )
        outcome = orch.run()
        assert outcome.detection_signal is True
    # Verify bot was disabled
    row = db.execute("SELECT bot_enabled FROM config WHERE id=1").fetchone()
    assert row["bot_enabled"] == 0
