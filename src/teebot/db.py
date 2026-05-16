"""SQLite schema and connection helpers."""
from __future__ import annotations

import sqlite3

REQUIRED_TABLES = ("requests", "bookings", "audit_log", "config")

_DDL = """
CREATE TABLE IF NOT EXISTS requests (
  id              INTEGER PRIMARY KEY AUTOINCREMENT,
  target_date     TEXT NOT NULL,
  course          TEXT NOT NULL,
  preferred_time  TEXT NOT NULL,
  window_start    TEXT NOT NULL,
  window_end      TEXT NOT NULL,
  status          TEXT NOT NULL,
  source_message_id TEXT,
  created_at      TIMESTAMP NOT NULL,
  updated_at      TIMESTAMP NOT NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_requests_pending_per_date
  ON requests(target_date) WHERE status='pending';

CREATE TABLE IF NOT EXISTS bookings (
  id                       INTEGER PRIMARY KEY AUTOINCREMENT,
  request_id               INTEGER NOT NULL REFERENCES requests(id),
  target_date              TEXT NOT NULL,
  booked_time              TEXT,
  course                   TEXT,
  foretees_reservation_id  TEXT,
  partner_status           TEXT NOT NULL DEFAULT 'pending_choice',
  partner_names            TEXT,
  attempt_count            INTEGER NOT NULL DEFAULT 0,
  booking_latency_ms       INTEGER,
  confirmation_message_id  TEXT,
  failure_reason           TEXT,
  created_at               TIMESTAMP NOT NULL
);

CREATE TABLE IF NOT EXISTS audit_log (
  id           INTEGER PRIMARY KEY AUTOINCREMENT,
  timestamp    TIMESTAMP NOT NULL,
  event_type   TEXT NOT NULL,
  request_id   INTEGER REFERENCES requests(id),
  booking_id   INTEGER REFERENCES bookings(id),
  details      TEXT,
  success      BOOLEAN NOT NULL
);

CREATE TABLE IF NOT EXISTS config (
  id            INTEGER PRIMARY KEY CHECK (id = 1),
  bot_enabled   BOOLEAN NOT NULL DEFAULT 1,
  use_browser   BOOLEAN NOT NULL DEFAULT 0,
  last_poll_at  TIMESTAMP
);
"""

_SEED_CONFIG = """
INSERT OR IGNORE INTO config (id, bot_enabled, use_browser)
  VALUES (1, 1, 0);
"""


def connect(db_path: str) -> sqlite3.Connection:
    """Open a SQLite connection with row_factory set to sqlite3.Row."""
    conn = sqlite3.connect(db_path, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


def init_schema(conn: sqlite3.Connection) -> None:
    """Idempotently create tables and seed the config row."""
    conn.executescript(_DDL)
    conn.execute(_SEED_CONFIG)
