"""Tests for db schema + connection helpers."""
import sqlite3
from pathlib import Path

import pytest

from teebot.db import connect, init_schema, REQUIRED_TABLES


def test_init_schema_creates_all_tables(tmp_path):
    db = tmp_path / "t.db"
    conn = connect(str(db))
    init_schema(conn)
    found = {r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    )}
    for t in REQUIRED_TABLES:
        assert t in found
    conn.close()


def test_init_schema_idempotent(tmp_path):
    db = tmp_path / "t.db"
    conn = connect(str(db))
    init_schema(conn)
    init_schema(conn)  # second call should not raise
    conn.close()


def test_config_row_inserted_on_init(tmp_path):
    db = tmp_path / "t.db"
    conn = connect(str(db))
    init_schema(conn)
    row = conn.execute("SELECT bot_enabled, use_browser FROM config WHERE id=1").fetchone()
    assert row[0] == 1   # enabled by default
    assert row[1] == 0   # browser fallback off by default
    conn.close()


def test_pending_per_date_constraint(tmp_path):
    """Two pending rows for the same date should fail — caller must handle upsert in app code."""
    db = tmp_path / "t.db"
    conn = connect(str(db))
    init_schema(conn)
    conn.execute("""
        INSERT INTO requests (target_date, course, preferred_time,
            window_start, window_end, status, created_at, updated_at)
        VALUES ('2026-05-24', 'Green', '09:00', '08:00', '10:00',
            'pending', '2026-05-15 12:00', '2026-05-15 12:00')
    """)
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("""
            INSERT INTO requests (target_date, course, preferred_time,
                window_start, window_end, status, created_at, updated_at)
            VALUES ('2026-05-24', 'Gold', '10:00', '09:00', '11:00',
                'pending', '2026-05-15 13:00', '2026-05-15 13:00')
        """)
    # But inserting a non-pending row should work
    conn.execute("""
        INSERT INTO requests (target_date, course, preferred_time,
            window_start, window_end, status, created_at, updated_at)
        VALUES ('2026-05-24', 'Gold', '10:00', '09:00', '11:00',
            'succeeded', '2026-05-15 13:00', '2026-05-15 13:00')
    """)
    conn.close()


def test_connect_sets_row_factory(tmp_path):
    db = tmp_path / "t.db"
    conn = connect(str(db))
    init_schema(conn)
    conn.execute("""
        INSERT INTO requests (target_date, course, preferred_time,
            window_start, window_end, status, created_at, updated_at)
        VALUES ('2026-05-24', 'Green', '09:00', '08:00', '10:00',
            'pending', '2026-05-15 12:00', '2026-05-15 12:00')
    """)
    row = conn.execute("SELECT * FROM requests WHERE target_date='2026-05-24'").fetchone()
    # Row factory should let us access columns by name
    assert row["course"] == "Green"
    conn.close()
