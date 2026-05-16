"""The 5-phase booker orchestrator that runs daily at 7:58 AM Central."""
from __future__ import annotations

import sqlite3
import time
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

from .audit import log_event
from .foretees.auth import AuthError, login
from .foretees.session import DetectionSignal, ForeTeesSession


@dataclass
class BookerOutcome:
    skipped: bool = False
    skipped_reason: str = ""
    booked_time: str | None = None
    booked_course: str | None = None
    attempt_count: int = 0
    detection_signal: bool = False
    error_message: str | None = None


class BookerOrchestrator:
    def __init__(
        self,
        *,
        db: sqlite3.Connection,
        today: date,
        target_offset_days: int,
        member_id: str,
        member_name: str,
        member_user: str,
        foretees_username: str,
        foretees_password: str,
    ):
        self.db = db
        self.today = today
        self.target_offset_days = target_offset_days
        self.member_id = member_id
        self.member_name = member_name
        self.member_user = member_user
        self.foretees_username = foretees_username
        self.foretees_password = foretees_password

    def _target_date(self) -> date:
        return self.today + timedelta(days=self.target_offset_days)

    def _audit(self, event: str, **kw) -> None:
        details = {k: v for k, v in kw.items() if k not in ("success", "request_id", "booking_id")}
        log_event(
            self.db,
            event,
            success=kw.get("success", True),
            request_id=kw.get("request_id"),
            booking_id=kw.get("booking_id"),
            details=details or None,
        )

    def _hard_stop(self, reason: str) -> None:
        """Disable the bot in the config table; called on any detection signal."""
        self.db.execute("UPDATE config SET bot_enabled = 0")
        self._audit("hard_stop", success=False, reason=reason)

    def run(self) -> BookerOutcome:
        outcome = BookerOutcome()

        # === Phase 1: Pre-flight ===
        cfg = self.db.execute("SELECT bot_enabled FROM config WHERE id=1").fetchone()
        if cfg is None or cfg["bot_enabled"] == 0:
            outcome.skipped = True
            outcome.skipped_reason = "bot_disabled"
            self._audit("preflight_skipped", success=True, reason="bot_disabled")
            return outcome

        target = self._target_date()
        req = self.db.execute(
            "SELECT * FROM requests WHERE target_date = ? AND status = 'pending'",
            (target.isoformat(),),
        ).fetchone()
        if req is None:
            outcome.skipped = True
            outcome.skipped_reason = "no_pending_request"
            self._audit("preflight_skipped", success=True, reason="no_pending_request",
                        target_date=target.isoformat())
            return outcome

        self._audit("preflight_ok", success=True, request_id=req["id"], target_date=target.isoformat())

        # === Phase 2: Auth ===
        try:
            with ForeTeesSession(audit_hook=lambda evt, **kw: self._audit(evt, success=True, **kw)) as sess:
                try:
                    auth_result = login(
                        sess,
                        username=self.foretees_username,
                        password=self.foretees_password,
                    )
                except DetectionSignal as ds:
                    outcome.detection_signal = True
                    outcome.error_message = str(ds)
                    self._hard_stop(f"auth: {ds}")
                    return outcome
                except AuthError as e:
                    outcome.error_message = f"auth_failed: {e}"
                    self._audit("auth_failed", success=False, error=str(e))
                    self.db.execute(
                        "UPDATE requests SET status='failed', updated_at=? WHERE id=?",
                        (datetime.utcnow().isoformat(), req["id"]),
                    )
                    return outcome
                self._audit("auth_ok", success=True, landing=auth_result.foretees_landing_url, request_id=req["id"])

                # Phases 3-5 added in Task 14
                # For now: mark the request 'attempted'
                self.db.execute(
                    "UPDATE requests SET status='attempted', updated_at=? WHERE id=?",
                    (datetime.utcnow().isoformat(), req["id"]),
                )
        except Exception as e:
            outcome.error_message = f"orchestrator_error: {e}"
            self._audit("orchestrator_error", success=False, error=str(e))

        return outcome
