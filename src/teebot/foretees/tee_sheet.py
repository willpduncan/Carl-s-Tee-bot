"""Fetch and parse the Member_sheet tee-sheet listing."""
from __future__ import annotations

import html
import json
import re
from dataclasses import dataclass
from datetime import date

from bs4 import BeautifulSoup

from .session import ForeTeesSession

TEE_SHEET_URL_TEMPLATE = (
    "https://www1.foretees.com/v5/pfcc_golf_m56/Member_sheet"
    "?calDate={cal_date}&course=-ALL-&showAvail=-1&displayOpt=0"
)


@dataclass(frozen=True)
class Slot:
    time: str            # 'HH:MM' 24-hour
    course: str
    ttdata: str
    index: int
    day_of_week: str
    available: bool


def fetch_tee_sheet_html(session: ForeTeesSession, target: date) -> str:
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


def parse_tee_sheet(html_text: str) -> list[Slot]:
    """Extract all bookable slot records from the Member_sheet HTML.

    The ForeTees tee-sheet encodes each available slot as an anchor tag with
    class ``teetime_button`` and a ``data-ftjson`` attribute containing a JSON
    object.  The relevant fields in that JSON are:

    * ``ttdata``  – opaque security token required for the booking POST
    * ``index``   – per-course slot index (integer)
    * ``course``  – course name string
    * ``day``     – day-of-week string (e.g. "Wednesday")
    * ``time:0``  – slot time in 12-hour format (e.g. "7:00 AM")

    Booked (unavailable) slots render as plain ``<span class="time_text">``
    elements with no ``data-ftjson``; those are *not* included in the output.

    Returns a list of :class:`Slot` instances (one per bookable time slot).
    """
    soup = BeautifulSoup(html_text, "lxml")
    slots: list[Slot] = []

    for anchor in soup.find_all("a", class_="teetime_button"):
        raw_json = anchor.get("data-ftjson", "")
        if not raw_json:
            continue
        try:
            data = json.loads(raw_json)
        except json.JSONDecodeError:
            continue

        ttdata = data.get("ttdata", "")
        if not ttdata:
            continue

        time_12h = data.get("time:0", "")
        if not time_12h:
            continue

        try:
            time_24h = _to_24h(time_12h)
        except ValueError:
            continue

        course = data.get("course", "")
        day = data.get("day", "")
        raw_index = data.get("index", None)
        if raw_index is None:
            continue
        try:
            index = int(raw_index)
        except (TypeError, ValueError):
            continue

        slots.append(
            Slot(
                time=time_24h,
                course=course,
                ttdata=ttdata,
                index=index,
                day_of_week=day,
                available=True,
            )
        )

    return slots
