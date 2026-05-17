"""Submit the final booking POST to Member_slot."""
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
) -> BookingResult:
    """POST Member_slot with the full booking payload (Carl + 3 TBDs).

    Returns a BookingResult; never raises (network errors → success=False).
    """
    # Per-player arrays — ForeTees expects fields like player_a, user_a, etc.
    # to appear N times (multi-value), one per player slot. Carl is player 1;
    # other 4 spots stay empty (TBD/blank).
    PLAYERS = 5
    player_a = [member_name] + [""] * (PLAYERS - 1)
    user_a = [member_user] + [""] * (PLAYERS - 1)
    member_id_a = [member_id] + [""] * (PLAYERS - 1)
    player_type_a = ["Member"] + [""] * (PLAYERS - 1)
    pcw_a = ["CRT"] + [""] * (PLAYERS - 1)
    p9_a = ["18"] + ["18"] * (PLAYERS - 1)
    guest_id_a = [""] * PLAYERS
    custom_disp_a = [""] * PLAYERS

    # Build form data; dict-with-list-values encodes multi-value form fields
    # like player_a=Carl&player_a=&player_a=...
    payload: dict[str, object] = {k: str(v) for k, v in form.callback_map.items()}
    payload["id_list"] = form.id_list
    payload["id_hash"] = form.id_hash
    payload["hide_notes"] = "0"
    payload["notes"] = ""
    payload["player_a"] = player_a
    payload["user_a"] = user_a
    payload["member_id_a"] = member_id_a
    payload["player_type_a"] = player_type_a
    payload["pcw_a"] = pcw_a
    payload["p9_a"] = p9_a
    payload["guest_id_a"] = guest_id_a
    payload["custom_disp_a"] = custom_disp_a

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
        body = json.loads(text)
        if isinstance(body, dict):
            if body.get("status") == "success" or "reservation_id" in body:
                return BookingResult(
                    success=True,
                    reservation_id=body.get("reservation_id") or body.get("id"),
                    raw_response=text,
                )
            # If ForeTees returned the slot-form config instead of a booking
            # result, our submit didn't trigger "submit" mode. Bail rather
            # than hammering every slot with the same broken request.
            if "show_member_tbd" in body or "page_title" in body or "slot_url" in body:
                return BookingResult(
                    success=False,
                    error_message="server returned slot-form config (submit mode not engaged)",
                    unexpected_response=True,
                    raw_response=text,
                )
            err = body.get("error") or body.get("message") or ""
            return BookingResult(
                success=False,
                error_message=str(err),
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
