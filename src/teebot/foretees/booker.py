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
    # Build payload from callback_map + per-player fields
    payload = dict(form.callback_map)  # copy
    payload["id_list"] = form.id_list
    payload["id_hash"] = form.id_hash
    payload["hide_notes"] = ""
    payload["notes"] = ""

    # Player 1 = Carl
    payload["player_a"] = member_name
    payload["user_a"] = member_user
    payload["member_id_a"] = member_id
    payload["player_type_a"] = "Member"
    payload["pcw_a"] = "CRT"
    payload["p9_a"] = "18"
    payload["custom_disp_a"] = ""
    payload["guest_id_a"] = ""

    # Players 2-4 = TBD
    for letter in ("b", "c", "d"):
        payload[f"player_{letter}"] = "TBD"
        payload[f"user_{letter}"] = ""
        payload[f"member_id_{letter}"] = ""
        payload[f"player_type_{letter}"] = "TBD"
        payload[f"pcw_{letter}"] = ""
        payload[f"p9_{letter}"] = "18"
        payload[f"custom_disp_{letter}"] = ""
        payload[f"guest_id_{letter}"] = ""

    payload["json_mode"] = "true"

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
