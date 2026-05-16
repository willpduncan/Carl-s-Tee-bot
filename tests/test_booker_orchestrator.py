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


from teebot.foretees.tee_sheet import Slot
from teebot.foretees.slot_form import SlotFormData
from teebot.foretees.booker import BookingResult


def test_race_books_preferred_when_available(db):
    _insert_pending_request(db, date(2026, 5, 20))
    fake_slots = [
        Slot("08:00", "Green", "TKN_08", 1, "Wednesday", True),
        Slot("09:00", "Green", "TKN_09", 5, "Wednesday", True),
        Slot("09:08", "Green", "TKN_0908", 6, "Wednesday", True),
        Slot("10:00", "Green", "TKN_10", 11, "Wednesday", True),
    ]
    fake_form = SlotFormData("ID_L", "ID_H", {"date":"20260520","ttdata":"TKN_09","course":"Green","index":"5","time:0":"9:00 AM","day":"Wednesday"}, "")
    with patch("teebot.booker_orchestrator.login") as mock_login, \
         patch("teebot.booker_orchestrator.fetch_tee_sheet_html") as mock_fetch, \
         patch("teebot.booker_orchestrator.parse_tee_sheet") as mock_parse, \
         patch("teebot.booker_orchestrator.fetch_slot_form") as mock_slotform, \
         patch("teebot.booker_orchestrator.submit_booking") as mock_submit, \
         patch("teebot.booker_orchestrator._wait_until_T0") as mock_wait, \
         patch("teebot.booker_orchestrator._warm_hold") as mock_warm:
        mock_login.return_value = MagicMock(foretees_landing_url="http://www1.foretees.com/landed")
        mock_fetch.return_value = "<html/>"
        mock_parse.return_value = fake_slots
        mock_slotform.return_value = fake_form
        mock_submit.return_value = BookingResult(success=True, reservation_id="R123")
        mock_wait.return_value = None
        mock_warm.return_value = None
        orch = BookerOrchestrator(
            db=db, today=date(2026, 5, 15), target_offset_days=5,
            member_id="10326", member_name="Carl", member_user="6605",
            foretees_username="x", foretees_password="y",
        )
        outcome = orch.run()
        assert outcome.booked_time == "09:00"
        assert outcome.attempt_count == 1
    row = db.execute("SELECT status FROM requests WHERE target_date='2026-05-20'").fetchone()
    assert row["status"] == "succeeded"


def test_race_walks_outward_when_preferred_taken(db):
    _insert_pending_request(db, date(2026, 5, 20))
    fake_slots = [
        Slot("08:00", "Green", "TKN_08", 1, "Wednesday", True),
        Slot("09:00", "Green", "TKN_09", 5, "Wednesday", True),  # preferred
        Slot("09:08", "Green", "TKN_0908", 6, "Wednesday", True),
        Slot("10:00", "Green", "TKN_10", 11, "Wednesday", True),
    ]
    fake_form = SlotFormData("ID_L", "ID_H", {}, "")
    with patch("teebot.booker_orchestrator.login") as mock_login, \
         patch("teebot.booker_orchestrator.fetch_tee_sheet_html") as mock_fetch, \
         patch("teebot.booker_orchestrator.parse_tee_sheet") as mock_parse, \
         patch("teebot.booker_orchestrator.fetch_slot_form") as mock_slotform, \
         patch("teebot.booker_orchestrator.submit_booking") as mock_submit, \
         patch("teebot.booker_orchestrator._wait_until_T0") as mock_wait, \
         patch("teebot.booker_orchestrator._warm_hold") as mock_warm:
        mock_login.return_value = MagicMock(foretees_landing_url="x")
        mock_fetch.return_value = "<html/>"
        mock_parse.return_value = fake_slots
        mock_slotform.return_value = fake_form
        # First attempt fails ("slot taken"); second succeeds
        mock_submit.side_effect = [
            BookingResult(success=False, error_message="slot taken"),
            BookingResult(success=True, reservation_id="R987"),
        ]
        mock_wait.return_value = None
        mock_warm.return_value = None
        orch = BookerOrchestrator(
            db=db, today=date(2026, 5, 15), target_offset_days=5,
            member_id="10326", member_name="Carl", member_user="6605",
            foretees_username="x", foretees_password="y",
        )
        outcome = orch.run()
        assert outcome.attempt_count == 2
        # The successful booking should be 09:08 (closest to 09:00 after itself)
        assert outcome.booked_time == "09:08"


def test_race_all_slots_taken_marks_failed(db):
    _insert_pending_request(db, date(2026, 5, 20))
    fake_slots = [
        Slot("09:00", "Green", "T", 5, "Wednesday", True),
    ]
    fake_form = SlotFormData("ID_L", "ID_H", {}, "")
    with patch("teebot.booker_orchestrator.login") as mock_login, \
         patch("teebot.booker_orchestrator.fetch_tee_sheet_html"), \
         patch("teebot.booker_orchestrator.parse_tee_sheet", return_value=fake_slots), \
         patch("teebot.booker_orchestrator.fetch_slot_form", return_value=fake_form), \
         patch("teebot.booker_orchestrator.submit_booking", return_value=BookingResult(success=False, error_message="slot taken")), \
         patch("teebot.booker_orchestrator._wait_until_T0"), \
         patch("teebot.booker_orchestrator._warm_hold"):
        mock_login.return_value = MagicMock(foretees_landing_url="x")
        orch = BookerOrchestrator(
            db=db, today=date(2026, 5, 15), target_offset_days=5,
            member_id="10326", member_name="Carl", member_user="6605",
            foretees_username="x", foretees_password="y",
        )
        outcome = orch.run()
        assert outcome.booked_time is None
    row = db.execute("SELECT status FROM requests WHERE target_date='2026-05-20'").fetchone()
    assert row["status"] == "failed"
