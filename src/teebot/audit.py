"""Append-only audit log writer."""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from typing import Any


def log_event(
    conn: sqlite3.Connection,
    event_type: str,
    *,
    success: bool,
    request_id: int | None = None,
    booking_id: int | None = None,
    details: dict[str, Any] | None = None,
) -> None:
    """Append a row to audit_log. Never raises; failures are swallowed
    because the audit log must not break the main flow."""
    try:
        conn.execute(
            """INSERT INTO audit_log
                 (timestamp, event_type, request_id, booking_id, details, success)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (
                datetime.now(timezone.utc).isoformat(),
                event_type,
                request_id,
                booking_id,
                json.dumps(details) if details is not None else None,
                1 if success else 0,
            ),
        )
    except sqlite3.Error:
        # Audit failures should never break the caller; will be visible in journalctl
        import logging
        logging.exception("Failed to write audit log row")
