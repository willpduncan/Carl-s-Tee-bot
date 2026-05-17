"""Parse Carl's email requests into ParsedRequest dataclasses.

The parser is intentionally lenient — it accepts structured "Day: ..."
labels OR free-text "Sunday, Green, 8-10 AM, prefer 9". It rejects only
emails that are missing required fields or contain contradictions.
"""
from __future__ import annotations

import email
import email.policy
import re
from dataclasses import dataclass
from datetime import date, timedelta
from email.message import EmailMessage


class ParseError(ValueError):
    """Raised when a request email cannot be unambiguously parsed."""


@dataclass(frozen=True)
class ParsedRequest:
    target_date: date
    course: str            # 'Green' | 'Gold' | 'White'
    preferred_time: str    # 'HH:MM' (24-hour)
    window_start: str
    window_end: str
    source_message_id: str | None


_COURSES = ("green", "gold", "white")
_DAY_NAMES = (
    "monday", "tuesday", "wednesday", "thursday",
    "friday", "saturday", "sunday",
)
_MONTH_NAMES = (
    "january", "february", "march", "april", "may", "june",
    "july", "august", "september", "october", "november", "december",
)


def _msg_body(raw: bytes) -> tuple[str, str | None]:
    """Return (lowercased plain-text body, message-id)."""
    msg = email.message_from_bytes(raw, policy=email.policy.default)
    msg_id = msg.get("Message-ID")
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() == "text/plain":
                body = part.get_content()
                break
        else:
            body = msg.get_content()
    else:
        body = msg.get_content()
    return body.lower(), msg_id


def parse_cancel(raw: bytes) -> bool:
    """True iff the email body's first non-empty line is 'cancel'."""
    body, _ = _msg_body(raw)
    for line in body.splitlines():
        s = line.strip()
        if s:
            return s.split()[0] == "cancel"
    return False


def _extract_course(text: str) -> str:
    found = [c for c in _COURSES if re.search(rf"\b{c}\b", text)]
    if not found:
        raise ParseError("course not found (expected Green, Gold, or White)")
    if len(set(found)) > 1:
        raise ParseError(f"multiple courses mentioned: {found}")
    return found[0].capitalize()


def _extract_target_date(text: str, today: date) -> date:
    """Find a date reference in the text and resolve it to a specific date.

    Accepts:
      - 'Sunday' / 'Sun' (next occurrence)
      - 'Sunday May 24' / 'May 24' / '5/24'
      - 'Thursday May 28'
    """
    # Try absolute "<Month> <day>" first
    months_re = "|".join(_MONTH_NAMES)
    m = re.search(rf"\b({months_re})\s+(\d{{1,2}})\b", text)
    if m:
        mon = _MONTH_NAMES.index(m.group(1)) + 1
        day = int(m.group(2))
        try:
            cand = date(today.year, mon, day)
            if cand < today:
                cand = date(today.year + 1, mon, day)
        except ValueError:
            raise ParseError(f"invalid month/day: {m.group(0)}")
        return cand
    # Try "M/D" e.g. "5/24"
    m = re.search(r"\b(\d{1,2})/(\d{1,2})\b", text)
    if m:
        mon, day = int(m.group(1)), int(m.group(2))
        try:
            cand = date(today.year, mon, day)
            if cand < today:
                cand = date(today.year + 1, mon, day)
        except ValueError:
            raise ParseError(f"invalid date: {m.group(0)}")
        return cand
    # Fall back to day-of-week → next occurrence
    for dow_idx, dow in enumerate(_DAY_NAMES):
        if re.search(rf"\b{dow}\b", text) or re.search(rf"\b{dow[:3]}\b", text):
            days_ahead = (dow_idx - today.weekday()) % 7
            if days_ahead == 0:
                days_ahead = 7
            return today + timedelta(days=days_ahead)
    raise ParseError("no date/day-of-week reference found")


_TIME_RE = re.compile(r"(\d{1,2})(?::(\d{2}))?\s*(am|pm)?", re.IGNORECASE)


def _parse_time(token: str) -> str:
    m = _TIME_RE.fullmatch(token.strip())
    if not m:
        raise ParseError(f"unrecognized time: {token!r}")
    hour = int(m.group(1))
    minute = int(m.group(2)) if m.group(2) else 0
    ampm = (m.group(3) or "").lower()
    if ampm == "pm" and hour != 12:
        hour += 12
    elif ampm == "am" and hour == 12:
        hour = 0
    elif not ampm:
        # Bare number: assume AM for 6-11, PM for 12-5, else AM
        if 1 <= hour <= 5:
            hour += 12
    if not (0 <= hour < 24 and 0 <= minute < 60):
        raise ParseError(f"time out of range: {token!r}")
    return f"{hour:02d}:{minute:02d}"


def _extract_window_and_preferred(text: str) -> tuple[str, str, str | None]:
    # Look for "X to Y", "X-Y", "between X and Y", or "Window: X Y" (whitespace-only)
    range_pats = [
        r"window[:\s]+(\d{1,2}(?::\d{2})?\s*(?:am|pm)?)\s*(?:to|-|–|—)\s*(\d{1,2}(?::\d{2})?\s*(?:am|pm)?)",
        r"between\s+(\d{1,2}(?::\d{2})?\s*(?:am|pm)?)\s+and\s+(\d{1,2}(?::\d{2})?\s*(?:am|pm)?)",
        r"(\d{1,2}(?::\d{2})?\s*(?:am|pm)?)\s*(?:to|-|–|—)\s*(\d{1,2}(?::\d{2})?\s*(?:am|pm)?)",
        # Lenient fallback: "Window: X Y" with just whitespace (Carl-friendly)
        r"window[:\s]+(\d{1,2}(?::\d{2})?\s*(?:am|pm)?)\s+(\d{1,2}(?::\d{2})?\s*(?:am|pm)?)",
    ]
    start = end = None
    for pat in range_pats:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            start = _parse_time(m.group(1))
            end = _parse_time(m.group(2))
            break
    if start is None:
        raise ParseError("time window (e.g. '8-10 AM' or 'between 8 and 10') not found")
    if start >= end:
        raise ParseError(f"window start {start} must be before end {end}")

    # Look for "prefer X" / "ideally X" / "Preferred: X"
    pref_pats = [
        r"prefer(?:red)?[:\s]+(\d{1,2}(?::\d{2})?\s*(?:am|pm)?)",
        r"ideally\s+(\d{1,2}(?::\d{2})?\s*(?:am|pm)?)",
    ]
    preferred = None
    for pat in pref_pats:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            preferred = _parse_time(m.group(1))
            break
    return start, end, preferred


def parse_request_email(raw: bytes, *, today: date) -> ParsedRequest:
    """Parse a request email, raising ParseError on any ambiguity."""
    body, msg_id = _msg_body(raw)
    course = _extract_course(body)
    target = _extract_target_date(body, today)
    # Reject dates beyond 14 days from today
    if target > today + timedelta(days=14):
        raise ParseError(
            f"target date {target} is too far in the future (more than 14 days)"
        )
    if target < today:
        raise ParseError(f"target date {target} is in the past")
    # Thursday: only Green or Gold allowed
    if target.weekday() == 3 and course == "White":
        raise ParseError("Thursdays at Pine Forest do not allow White course")

    start, end, preferred = _extract_window_and_preferred(body)
    if preferred is None:
        # Default to midpoint of the window
        s_h, s_m = map(int, start.split(":"))
        e_h, e_m = map(int, end.split(":"))
        mid_min = ((s_h * 60 + s_m) + (e_h * 60 + e_m)) // 2
        preferred = f"{mid_min // 60:02d}:{mid_min % 60:02d}"
    if not (start <= preferred <= end):
        raise ParseError(
            f"preferred time {preferred} must fall within window {start}-{end}"
        )

    return ParsedRequest(
        target_date=target,
        course=course,
        preferred_time=preferred,
        window_start=start,
        window_end=end,
        source_message_id=msg_id,
    )
