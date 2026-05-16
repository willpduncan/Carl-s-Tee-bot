"""Fetch and parse the Member_sheet tee-sheet listing.

Each bookable slot in the rendered HTML carries a ``data-ftjson`` attribute
containing a JSON object with all the Member_slot POST parameters needed
to book it — including the per-slot ``ttdata`` token. The parser extracts
those JSON blobs and translates each one into a Slot record.
"""
from __future__ import annotations

import html as html_module
import json
import re
from dataclasses import dataclass, field
from datetime import date

from .session import ForeTeesSession


TEE_SHEET_URL_TEMPLATE = (
    "https://www1.foretees.com/v5/pfcc_golf_m56/Member_sheet"
    "?calDate={cal_date}&course=-ALL-&showAvail=-1&displayOpt=0"
)


@dataclass(frozen=True)
class Slot:
    time: str            # 'HH:MM' 24-hour
    course: str          # e.g., 'Green to Gold'
    ttdata: str          # per-slot server-issued token (required for booking)
    index: int           # the 'jump' value from data-ftjson
    day_of_week: str     # empty if unknown; bot fills from the request's day
    available: bool      # True if wasP1 is empty (no existing primary player)
    raw_data: dict = field(default_factory=dict)  # full parsed data-ftjson payload


def fetch_tee_sheet_html(session: ForeTeesSession, target: date) -> str:
    """GET the Member_sheet endpoint for the target date."""
    cal_date = target.strftime("%m/%d/%Y")
    url = TEE_SHEET_URL_TEMPLATE.format(cal_date=cal_date)
    r = session.client.get(url)
    r.raise_for_status()
    return r.text


def _to_24h(time_12h: str) -> str:
    t = time_12h.strip().upper().replace(" ", "")
    m = re.match(r"(\d{1,2}):(\d{2})(AM|PM)", t)
    if not m:
        raise ValueError(f"unparseable time: {time_12h!r}")
    h = int(m.group(1))
    mi = int(m.group(2))
    if m.group(3) == "PM" and h != 12:
        h += 12
    elif m.group(3) == "AM" and h == 12:
        h = 0
    return f"{h:02d}:{mi:02d}"


_FTJSON_RE = re.compile(r'data-ftjson="([^"]+)"')


def _full_unescape(s: str) -> str:
    """HTML-unescape repeatedly until stable.

    Chrome's view-source export double-encodes attribute entities
    (&quot; → &amp;quot;), while a fresh HTTP response is single-encoded.
    The parser handles both by unescaping until idempotent.
    """
    prev = s
    for _ in range(5):
        cur = html_module.unescape(prev)
        if cur == prev:
            return cur
        prev = cur
    return prev


def parse_tee_sheet(html: str) -> list[Slot]:
    """Extract bookable Slot records from a Member_sheet response."""
    slots: list[Slot] = []
    for raw_attr in _FTJSON_RE.findall(html):
        decoded = _full_unescape(raw_attr)
        try:
            data = json.loads(decoded)
        except json.JSONDecodeError:
            continue
        if data.get("type") != "Member_slot":
            continue

        time_12h = data.get("time:0", "")
        try:
            time_24 = _to_24h(time_12h) if time_12h else ""
        except ValueError:
            continue
        if not time_24:
            continue

        ttdata = data.get("ttdata", "")
        if not ttdata:
            continue

        # Availability: wasP1 empty means no primary player has claimed the slot
        was_p1 = (data.get("wasP1") or "").strip()
        available = (was_p1 == "")

        slots.append(Slot(
            time=time_24,
            course=data.get("course", ""),
            ttdata=ttdata,
            index=int(data.get("jump", data.get("index", 0))),
            day_of_week="",
            available=available,
            raw_data=data,
        ))
    return slots
