"""Tests for audit log writer."""
import json

import pytest

from teebot.audit import log_event
from teebot.db import connect, init_schema


@pytest.fixture
def conn(tmp_path):
    c = connect(str(tmp_path / "t.db"))
    init_schema(c)
    yield c
    c.close()


def test_log_event_writes_row(conn):
    log_event(conn, "test_event", success=True, details={"foo": "bar"})
    row = conn.execute("SELECT * FROM audit_log").fetchone()
    assert row["event_type"] == "test_event"
    assert row["success"] == 1
    assert json.loads(row["details"]) == {"foo": "bar"}


def test_log_event_with_no_details(conn):
    log_event(conn, "no_details", success=True)
    row = conn.execute("SELECT * FROM audit_log").fetchone()
    assert row["details"] is None


def test_log_event_with_request_and_booking_id(conn):
    # Make a request row first so the FK is satisfied
    conn.execute("""
        INSERT INTO requests (id, target_date, course, preferred_time,
            window_start, window_end, status, created_at, updated_at)
        VALUES (1, '2026-05-24', 'Green', '09:00', '08:00', '10:00',
            'pending', '2026-05-15 12:00', '2026-05-15 12:00')
    """)
    log_event(conn, "request_received", request_id=1, success=True)
    row = conn.execute("SELECT request_id FROM audit_log").fetchone()
    assert row["request_id"] == 1


def test_log_event_failure_serializes_exception(conn):
    log_event(
        conn,
        "login_failed",
        success=False,
        details={"error": "connection refused", "status": 0}
    )
    row = conn.execute("SELECT * FROM audit_log").fetchone()
    assert row["success"] == 0
    payload = json.loads(row["details"])
    assert payload["error"] == "connection refused"
