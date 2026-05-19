"""Submit the final booking POST to Member_slot.

Wire format derived from a real captured submit (HAR entry 122 of
the 2026-05-19 capture). Critical fields that distinguish a submit
from a slot-click:
  - submitForm = "submit"
  - slot_submit_action = "update"

Per-player fields are NUMBERED 1-5 (not lettered a-d):
  - player1..player5    name (or "X" to block)
  - user1..user5        empty when booking self; non-empty for partner
  - member_id1..5       member id for self, "0" for X/empty
  - player_type_a1..5   empty for self-booking
  - p91..p95            0 = 18 holes, 1 = 9 holes
  - p1cw..p5cw          "CRT" = cart, others available
  - guest_id1..5        "0" = not a guest
"""
from __future__ import annotations

import json
from dataclasses import dataclass

from .session import ForeTeesSession
from .slot_form import SlotFormData, MEMBER_SLOT_URL
from .tee_sheet import Slot


@dataclass(frozen=True)
class BookingResult:
    success: bool
    reservation_id: str | None = None
    error_message: str | None = None
    unexpected_response: bool = False
    raw_response: str = ""


def submit_booking(
    session: ForeTeesSession,
    *,
    slot: Slot,
    form: SlotFormData,
    member_id: str,
    member_name: str,
    member_user: str,
    block_other_slots: bool = True,
) -> BookingResult:
    """POST Member_slot with the booking payload. Carl is player 1;
    other 4 slots are marked "X" (blocked) by default so no other member
    can join his group.

    If block_other_slots=False, other slots are left as empty TBDs.
    """
    # Player 1 = Carl
    payload: dict[str, str] = {
        "teecurr_id1": form.id_list,
        "id_hash": form.id_hash,
        "hide": "0",
        "notes": "",
        "submitForm": "submit",
        "slot_submit_action": "update",
        "json_mode": "true",
        "player1": member_name,
        "user1": "",
        "member_id1": member_id,
        "player_type_a1": "",
        "p91": "0",
        "p1cw": "CRT",
        "guest_id1": "0",
    }

    # Players 2-5 — X to block other members from joining, or empty for TBD
    fill_name = "X" if block_other_slots else ""
    for n in (2, 3, 4, 5):
        payload[f"player{n}"] = fill_name
        payload[f"user{n}"] = ""
        payload[f"member_id{n}"] = "0"
        payload[f"player_type_a{n}"] = ""
        payload[f"p9{n}"] = "0"
        payload[f"p{n}cw"] = "CRT"
        payload[f"guest_id{n}"] = "0"

    try:
        r = session.client.post(MEMBER_SLOT_URL, data=payload)
    except Exception as e:
        return BookingResult(success=False, error_message=f"network: {e}", raw_response="")

    if r.status_code != 200:
        return BookingResult(
            success=False,
            error_message=f"HTTP {r.status_code}",
            raw_response=r.text,
        )

    text = r.text
    import logging
    logging.getLogger("teebot.booker").info(
        "Booking POST response: status=%s ctype=%s body_snippet=%r",
        r.status_code,
        r.headers.get("content-type", "?"),
        text[:600],
    )

    # Try parsing as JSON first
    try:
        body = json.loads(text) if text else {}
        if isinstance(body, dict):
            # Slot-form config returned → submit didn't engage (bail)
            if "show_member_tbd" in body or "page_title" in body or "slot_url" in body:
                return BookingResult(
                    success=False,
                    error_message="server returned slot-form config (submit mode not engaged)",
                    unexpected_response=True,
                    raw_response=text,
                )
            # Explicit success markers
            if body.get("status") == "success" or "reservation_id" in body or "confirmation_id" in body:
                return BookingResult(
                    success=True,
                    reservation_id=(
                        body.get("reservation_id")
                        or body.get("confirmation_id")
                        or body.get("id")
                    ),
                    raw_response=text,
                )
            # Explicit error markers
            err = body.get("error") or body.get("message")
            if err:
                return BookingResult(
                    success=False,
                    error_message=str(err),
                    raw_response=text,
                )
            # JSON response that's not the slot-form config and not an
            # explicit error → ForeTees accepted the submit. Empty {}
            # responses are observed after successful bookings.
            return BookingResult(
                success=True,
                reservation_id=None,
                raw_response=text,
            )
    except json.JSONDecodeError:
        pass

    # HTML response: look for confirmation keywords
    lower = text.lower()
    if "reserved" in lower or "confirmation" in lower:
        return BookingResult(
            success=True,
            reservation_id=None,
            raw_response=text,
        )
    if "already taken" in lower or "no longer available" in lower:
        return BookingResult(
            success=False,
            error_message="slot taken",
            raw_response=text,
        )
    # Anything else: mark as unexpected
    return BookingResult(
        success=False,
        error_message="unexpected response shape",
        unexpected_response=True,
        raw_response=text,
    )
