"""POST Member_slot (slot-click), parse the returned form for ids."""
from __future__ import annotations

import html as htmllib
import json
import re
from dataclasses import dataclass

from .session import ForeTeesSession
from .tee_sheet import Slot

MEMBER_SLOT_URL = "https://www1.foretees.com/v5/pfcc_golf_m56/Member_slot"


@dataclass(frozen=True)
class SlotFormData:
    id_list: str
    id_hash: str
    callback_map: dict[str, str]
    raw_html: str


def fetch_slot_form(session: ForeTeesSession, slot: Slot, target_date_str: str) -> SlotFormData:
    """POST Member_slot to render the slot's booking form.

    Uses the raw data-ftjson payload from the tee-sheet listing if available
    (most accurate — mirrors what the browser sends). Falls back to a
    field-by-field reconstruction if raw_data wasn't captured.
    """
    if slot.raw_data:
        # Build payload from the captured data-ftjson, dropping the 'type' key
        # which is a client-side marker, not a server field.
        payload = {k: ("" if v is None else str(v))
                   for k, v in slot.raw_data.items() if k != "type"}
        # Ensure these are present
        payload.setdefault("contimes", "1")
        payload.setdefault("day", slot.day_of_week)
    else:
        payload = {
            "lstate": "0",
            "newreq": "yes",
            "displayOpt": "0",
            "showAvail": "-1",
            "ttdata": slot.ttdata,
            "date": target_date_str,
            "index": str(slot.index),
            "course": slot.course,
            "returnCourse": "-ALL-",
            "wasP1": "", "wasP2": "", "wasP3": "", "wasP4": "", "wasP5": "",
            "p5": "Yes",
            "time:0": _to_12h(slot.time),
            "day": slot.day_of_week,
            "contimes": "1",
        }
    r = session.client.post(MEMBER_SLOT_URL, data=payload)
    r.raise_for_status()
    return parse_slot_form(r.text)


def _to_12h(t24: str) -> str:
    h, m = map(int, t24.split(":"))
    ampm = "AM" if h < 12 else "PM"
    h12 = h % 12 or 12
    return f"{h12}:{m:02d} {ampm}"


def parse_slot_form(html: str) -> SlotFormData:
    """Extract id_list, id_hash, and callback_map from the slot-form HTML.

    The ForeTees slot-form page embeds all booking data as a JSON blob in a
    ``data-ftjson`` attribute on the ``.slot_container`` div.  The attribute
    value is HTML-entity encoded, so we decode it before parsing.

    Structure:
      data-ftjson="{...}"
        id_list: ["<base64-encoded id>", ...]   — take index 0
        id_hash: "<base64-encoded hash>"
        callback_map: {<key: value pairs for the follow-up POST>}
    """
    # Find the data-ftjson attribute (value is HTML-entity encoded)
    m = re.search(r'data-ftjson="([^"]+)"', html)
    if not m:
        raise RuntimeError("Could not find data-ftjson attribute in slot form response")

    decoded = htmllib.unescape(m.group(1))
    data = json.loads(decoded)

    # id_list is a JSON array; take the first element
    raw_id_list = data.get("id_list", [])
    id_list = raw_id_list[0] if raw_id_list else ""

    id_hash: str = data.get("id_hash", "")

    callback_map: dict[str, str] = data.get("callback_map", {})

    if not id_list or not id_hash:
        raise RuntimeError(
            "Could not extract id_list or id_hash from slot form response"
        )

    return SlotFormData(
        id_list=id_list,
        id_hash=id_hash,
        callback_map=callback_map,
        raw_html=html,
    )
