"""The 5-phase booker orchestrator that runs daily at 7:58 AM Central."""
from __future__ import annotations

import sqlite3
import time
from dataclasses import dataclass
from datetime import date, datetime, time as dtime, timedelta
from zoneinfo import ZoneInfo

from .audit import log_event
from .foretees.auth import AuthError, login
from .foretees.session import DetectionSignal, ForeTeesSession
from .foretees.tee_sheet import Slot, fetch_tee_sheet_html, parse_tee_sheet
from .foretees.slot_form import SlotFormData, fetch_slot_form
from .foretees.booker import BookingResult, submit_booking


@dataclass
class BookerOutcome:
    skipped: bool = False
    skipped_reason: str = ""
    booked_time: str | None = None
    booked_course: str | None = None
    booked_reservation_id: str | None = None
    attempt_count: int = 0
    detection_signal: bool = False
    error_message: str | None = None
    booking_id: int | None = None


def _time_to_minutes(t: str) -> int:
    h, m = map(int, t.split(":"))
    return h * 60 + m


def _wait_until_T0(target_dt: datetime) -> None:
    """Sleep until target_dt with sub-second precision."""
    while True:
        now = datetime.now(target_dt.tzinfo)
        remaining = (target_dt - now).total_seconds()
        if remaining <= 0:
            return
        if remaining > 1.0:
            time.sleep(remaining - 0.5)
        else:
            time.sleep(0.001)


def _warm_hold(session: ForeTeesSession, until_dt: datetime, ping_url: str) -> None:
    """Keep session warm by pinging a benign endpoint every 20s."""
    while True:
        now = datetime.now(until_dt.tzinfo)
        if now >= until_dt:
            return
        try:
            session.client.get(ping_url)
        except Exception:
            pass
        sleep_for = min(20.0, (until_dt - now).total_seconds() - 5.0)
        if sleep_for <= 0:
            return
        time.sleep(sleep_for)


def _prioritize_slots(
    slots: list[Slot],
    course: str,
    preferred: str,
    window_start: str,
    window_end: str,
) -> list[Slot]:
    """Return slots that match course + fall within window, sorted by closeness to preferred."""
    pref_min = _time_to_minutes(preferred)
    ws_min = _time_to_minutes(window_start)
    we_min = _time_to_minutes(window_end)

    matched: list[tuple[int, Slot]] = []
    for s in slots:
        if not s.available:
            continue
        if course.lower() not in s.course.lower():
            continue
        m = _time_to_minutes(s.time)
        if not (ws_min <= m <= we_min):
            continue
        matched.append((abs(m - pref_min), s))
    matched.sort(key=lambda x: x[0])
    return [s for _, s in matched]


class BookerOrchestrator:
    BENIGN_PING_URL = "https://www1.foretees.com/v5/pfcc_golf_m56/Member_announce"

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
        tz: str = "America/Chicago",
        race_at_local_time: dtime = dtime(8, 0, 0),
    ):
        self.db = db
        self.today = today
        self.target_offset_days = target_offset_days
        self.member_id = member_id
        self.member_name = member_name
        self.member_user = member_user
        self.foretees_username = foretees_username
        self.foretees_password = foretees_password
        self.tz = ZoneInfo(tz)
        self.race_at_local_time = race_at_local_time

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
        request_id = req["id"]
        self._audit("preflight_ok", success=True, request_id=request_id,
                    target_date=target.isoformat())

        # === Phase 2: Auth + outer DetectionSignal catch (covers phases 2-4) ===
        with ForeTeesSession(audit_hook=lambda evt, **kw: self._audit(evt, success=True, **kw)) as sess:
            try:
                try:
                    auth_result = login(sess, username=self.foretees_username, password=self.foretees_password)
                except AuthError as e:
                    outcome.error_message = f"auth_failed: {e}"
                    self._audit("auth_failed", success=False, error=str(e), request_id=request_id)
                    self.db.execute(
                        "UPDATE requests SET status='failed', updated_at=? WHERE id=?",
                        (datetime.utcnow().isoformat(), request_id),
                    )
                    return outcome
                self._audit("auth_ok", success=True, landing=auth_result.foretees_landing_url,
                            request_id=request_id)

                # === Phase 3: Warm hold ===
                race_dt = datetime.combine(self.today, self.race_at_local_time, tzinfo=self.tz)
                warm_until = race_dt - timedelta(seconds=5)
                _warm_hold(sess, warm_until, self.BENIGN_PING_URL)
                self._audit("warm_hold_complete", success=True, request_id=request_id)

                # === Phase 4: Race ===
                _wait_until_T0(race_dt)
                t0_monotonic = time.monotonic()
                tee_sheet_html = fetch_tee_sheet_html(sess, target)
                slots = parse_tee_sheet(tee_sheet_html)
                self._audit("tee_sheet_fetched", success=True, slot_count=len(slots), request_id=request_id)

                prioritized = _prioritize_slots(
                    slots,
                    course=req["course"],
                    preferred=req["preferred_time"],
                    window_start=req["window_start"],
                    window_end=req["window_end"],
                )
                self._audit("slots_prioritized", success=True,
                            candidate_count=len(prioritized), request_id=request_id)

                target_date_str = target.strftime("%Y%m%d")
                attempts = 0
                successful_slot: Slot | None = None
                successful_result: BookingResult | None = None
                for slot in prioritized:
                    attempts += 1
                    self._audit("slot_attempt", success=True, slot_time=slot.time,
                                attempt=attempts, request_id=request_id)
                    try:
                        form = fetch_slot_form(sess, slot, target_date_str)
                    except DetectionSignal:
                        raise
                    except Exception as e:
                        self._audit("slot_form_failed", success=False, error=str(e),
                                    slot_time=slot.time, request_id=request_id)
                        continue
                    result = submit_booking(
                        sess,
                        slot=slot,
                        form=form,
                        member_id=self.member_id,
                        member_name=self.member_name,
                        member_user=self.member_user,
                    )
                    self._audit("booking_attempted", success=result.success,
                                slot_time=slot.time, result_msg=result.error_message,
                                request_id=request_id)
                    if result.success:
                        successful_slot = slot
                        successful_result = result
                        break
                    if result.unexpected_response:
                        self._audit("stop_due_to_unexpected", success=False,
                                    request_id=request_id)
                        break
                latency_ms = int((time.monotonic() - t0_monotonic) * 1000)
            except DetectionSignal as ds:
                outcome.detection_signal = True
                outcome.error_message = str(ds)
                self._hard_stop(f"detection: {ds}")
                return outcome

            # === Phase 5: Confirm ===
            outcome.attempt_count = attempts
            if successful_slot is not None and successful_result is not None:
                cur = self.db.execute(
                    """INSERT INTO bookings
                         (request_id, target_date, booked_time, course,
                          foretees_reservation_id, attempt_count, booking_latency_ms, created_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        request_id, target.isoformat(),
                        successful_slot.time, successful_slot.course,
                        successful_result.reservation_id, attempts,
                        latency_ms, datetime.utcnow().isoformat(),
                    ),
                )
                outcome.booking_id = cur.lastrowid
                outcome.booked_time = successful_slot.time
                outcome.booked_course = successful_slot.course
                outcome.booked_reservation_id = successful_result.reservation_id
                self.db.execute(
                    "UPDATE requests SET status='succeeded', updated_at=? WHERE id=?",
                    (datetime.utcnow().isoformat(), request_id),
                )
                self._audit("booking_succeeded", success=True, request_id=request_id,
                            booking_id=outcome.booking_id, latency_ms=latency_ms)
            else:
                self.db.execute(
                    """INSERT INTO bookings
                         (request_id, target_date, attempt_count, booking_latency_ms,
                          failure_reason, created_at)
                       VALUES (?, ?, ?, ?, ?, ?)""",
                    (
                        request_id, target.isoformat(),
                        attempts, latency_ms,
                        outcome.error_message or "no_slots_in_window",
                        datetime.utcnow().isoformat(),
                    ),
                )
                self.db.execute(
                    "UPDATE requests SET status='failed', updated_at=? WHERE id=?",
                    (datetime.utcnow().isoformat(), request_id),
                )
                self._audit("booking_failed", success=False, request_id=request_id,
                            attempts=attempts)

        return outcome
