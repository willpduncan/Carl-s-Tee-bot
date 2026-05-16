"""IMAP poller: classifies inbound messages and updates DB + sends replies."""
from __future__ import annotations

import email
import email.policy
import json
import re
import sqlite3
from dataclasses import dataclass
from datetime import date, datetime

from .audit import log_event
from .inbox import Inbox, RawMessage
from .mailer import Mailer, OutgoingEmail
from .parser import ParseError, parse_cancel, parse_request_email


_FORMAT_HELP = """\
I couldn't understand your message. Please send it in this format:

  Day: Sunday May 24
  Course: Green
  Window: 8:00 AM to 10:00 AM
  Preferred: 9:00 AM

Or free-text like: "Sunday, Green, 8-10 AM, prefer 9".
"""


_NAMES_RE = re.compile(r"names\s*[:\s]\s*(.+)", re.IGNORECASE)


class PollerOrchestrator:
    def __init__(
        self,
        *,
        db: sqlite3.Connection,
        inbox: Inbox,
        mailer: Mailer,
        bot_email: str,
        carl_email: str,
        today: date,
    ):
        self.db = db
        self.inbox = inbox
        self.mailer = mailer
        self.bot_email = bot_email
        self.carl_email = carl_email
        self.today = today

    def _audit(self, event: str, **kw) -> None:
        log_event(
            self.db, event,
            success=kw.pop("success", True),
            request_id=kw.pop("request_id", None),
            booking_id=kw.pop("booking_id", None),
            details=kw or None,
        )

    def _get_in_reply_to(self, raw: bytes) -> str | None:
        msg = email.message_from_bytes(raw, policy=email.policy.default)
        return msg.get("In-Reply-To")

    def _find_booking_by_confirmation_id(self, msg_id: str) -> sqlite3.Row | None:
        return self.db.execute(
            "SELECT * FROM bookings WHERE confirmation_message_id = ?",
            (msg_id,),
        ).fetchone()

    def _handle_partner_reply(self, raw: bytes, booking: sqlite3.Row, *, in_reply_to: str) -> None:
        body = email.message_from_bytes(raw, policy=email.policy.default).get_content().lower()
        if "names" in body:
            m = _NAMES_RE.search(body)
            if m:
                names_str = m.group(1).strip()
                names = [n.strip() for n in re.split(r"[,;]| and ", names_str) if n.strip()]
                # Title-case each name back since body was lowercased
                names = [' '.join(w.capitalize() for w in n.split()) for n in names]
                self.db.execute(
                    "UPDATE bookings SET partner_status='names_provided', partner_names=? WHERE id=?",
                    (json.dumps(names), booking["id"]),
                )
                ack = f"Got it. Names recorded: {', '.join(names)}.\n\nYou can edit anytime in ForeTees."
                self._audit("partner_names_set", booking_id=booking["id"], names=names)
        elif "leave open" in body or re.search(r"\bopen\b", body):
            self.db.execute(
                "UPDATE bookings SET partner_status='leave_open' WHERE id=?",
                (booking["id"],),
            )
            ack = "OK, the other 3 spots will stay open. You can edit anytime in ForeTees."
            self._audit("partner_leave_open", booking_id=booking["id"])
        elif "tbd" in body:
            self.db.execute(
                "UPDATE bookings SET partner_status='all_tbd' WHERE id=?",
                (booking["id"],),
            )
            ack = "OK, the other 3 spots are TBD. You can edit anytime in ForeTees."
            self._audit("partner_all_tbd", booking_id=booking["id"])
        else:
            ack = (
                "I didn't recognize your choice. Reply with one of:\n"
                "  - 'leave open'\n"
                "  - 'TBD'\n"
                "  - 'names: Bob, Tom, Jim'"
            )
            self._audit("partner_unparseable", success=False, booking_id=booking["id"])
        self.mailer.send(OutgoingEmail(
            to=self.carl_email,
            subject="Re: tee time partner choice",
            body=ack,
            in_reply_to=in_reply_to,
            from_address=self.bot_email,
        ))

    def _handle_cancel(self, msg: RawMessage) -> None:
        self.db.execute(
            "UPDATE requests SET status='cancelled', updated_at=? WHERE status='pending'",
            (datetime.utcnow().isoformat(),),
        )
        self.mailer.send(OutgoingEmail(
            to=self.carl_email,
            subject="Cancelled",
            body="Your pending request has been cancelled.",
            from_address=self.bot_email,
        ))
        self._audit("request_cancelled", uid=msg.uid)

    def _handle_request(self, msg: RawMessage) -> None:
        try:
            parsed = parse_request_email(msg.raw, today=self.today)
        except ParseError as e:
            self._audit("parse_failed", success=False, uid=msg.uid, error=str(e))
            self.mailer.send(OutgoingEmail(
                to=self.carl_email,
                subject="Re: tee time",
                body=_FORMAT_HELP + f"\n(Details: {e})",
                from_address=self.bot_email,
            ))
            return

        # Upsert: cancel any existing pending row for this target_date, then insert
        self.db.execute(
            "UPDATE requests SET status='cancelled', updated_at=? "
            "WHERE target_date=? AND status='pending'",
            (datetime.utcnow().isoformat(), parsed.target_date.isoformat()),
        )
        cur = self.db.execute(
            """INSERT INTO requests
                 (target_date, course, preferred_time, window_start, window_end,
                  status, source_message_id, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, 'pending', ?, ?, ?)""",
            (
                parsed.target_date.isoformat(),
                parsed.course,
                parsed.preferred_time,
                parsed.window_start,
                parsed.window_end,
                parsed.source_message_id,
                datetime.utcnow().isoformat(),
                datetime.utcnow().isoformat(),
            ),
        )
        rid = cur.lastrowid
        self._audit("request_received", request_id=rid, target_date=parsed.target_date.isoformat())
        confirm_body = (
            f"Got it, Carl.\n\n"
            f"  Day:       {parsed.target_date.strftime('%A, %B %d')}\n"
            f"  Course:    {parsed.course}\n"
            f"  Window:    {parsed.window_start} to {parsed.window_end}\n"
            f"  Preferred: {parsed.preferred_time}\n\n"
            "I'll try to book this at 8:00 AM Central on the booking morning.\n\n"
            "To cancel, reply with \"cancel\". To change, just send a new email."
        )
        self.mailer.send(OutgoingEmail(
            to=self.carl_email,
            subject="Re: tee time",
            body=confirm_body,
            from_address=self.bot_email,
            in_reply_to=parsed.source_message_id,
        ))

    def run_once(self) -> None:
        import logging
        log = logging.getLogger("teebot.poller")

        messages = self.inbox.fetch_unread()
        if messages:
            log.info("Found %d unread message(s) to process", len(messages))
        for msg in messages:
            log.info("Processing UID=%s from sender=%s", msg.uid, msg.sender)
            try:
                in_reply_to = self._get_in_reply_to(msg.raw)
                if in_reply_to:
                    booking = self._find_booking_by_confirmation_id(in_reply_to)
                    if booking is not None:
                        log.info("Handling as partner reply (booking_id=%s)", booking["id"])
                        self._handle_partner_reply(msg.raw, booking, in_reply_to=in_reply_to)
                        self.inbox.mark_seen(msg.uid)
                        continue
                # Not a partner reply — classify as cancel or request
                if parse_cancel(msg.raw):
                    log.info("Handling as cancel request")
                    self._handle_cancel(msg)
                else:
                    log.info("Handling as new tee-time request")
                    self._handle_request(msg)
                log.info("Successfully processed UID=%s", msg.uid)
            except Exception as e:
                log.exception("Failed to process UID=%s: %s", msg.uid, e)
                self._audit("poller_error", success=False, uid=msg.uid, error=str(e))
            finally:
                self.inbox.mark_seen(msg.uid)
        self.db.execute(
            "UPDATE config SET last_poll_at=? WHERE id=1",
            (datetime.utcnow().isoformat(),),
        )
