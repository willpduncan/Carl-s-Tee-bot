"""Tests for the booking submitter (uses real ForeTees wire format)."""
from unittest.mock import MagicMock
from urllib.parse import parse_qs

import httpx
import pytest

from teebot.foretees.booker import BookingResult, submit_booking
from teebot.foretees.session import ForeTeesSession
from teebot.foretees.slot_form import SlotFormData
from teebot.foretees.tee_sheet import Slot


@pytest.fixture
def slot():
    return Slot(
        time="09:08",
        course="Green to Gold",
        ttdata="TOKEN123",
        index=5,
        day_of_week="Sunday",
        available=True,
    )


@pytest.fixture
def slot_form():
    return SlotFormData(
        id_list="ID_LIST_VAL",
        id_hash="ID_HASH_VAL",
        callback_map={},
        raw_html="",
    )


def test_submit_booking_uses_correct_field_names(slot, slot_form):
    """The submit POST must use the numbered field names that real ForeTees expects."""
    submitted: dict[str, list[str]] = {}
    def handler(req: httpx.Request) -> httpx.Response:
        nonlocal submitted
        submitted = parse_qs(req.content.decode(), keep_blank_values=True)
        return httpx.Response(200, json={"status": "success", "reservation_id": "RES12345"})
    s = ForeTeesSession()
    s.client._transport = httpx.MockTransport(handler)
    result = submit_booking(
        s, slot=slot, form=slot_form,
        member_id="10326", member_name="Carl A Pfiffner", member_user="6605",
    )
    s.close()

    assert result.success
    # CSRF tokens
    assert submitted["teecurr_id1"] == ["ID_LIST_VAL"]
    assert submitted["id_hash"] == ["ID_HASH_VAL"]
    # Magic fields that distinguish submit from click
    assert submitted["submitForm"] == ["submit"]
    assert submitted["slot_submit_action"] == ["update"]
    # Player 1 = Carl
    assert submitted["player1"] == ["Carl A Pfiffner"]
    assert submitted["member_id1"] == ["10326"]
    assert submitted["p1cw"] == ["CRT"]
    # Players 2-5 default to "X" (block other members)
    assert submitted["player2"] == ["X"]
    assert submitted["player5"] == ["X"]
    assert submitted["member_id2"] == ["0"]


def test_submit_booking_can_leave_slots_open(slot, slot_form):
    """When block_other_slots=False, players 2-5 are empty (TBD), not X."""
    submitted: dict[str, list[str]] = {}
    def handler(req: httpx.Request) -> httpx.Response:
        nonlocal submitted
        submitted = parse_qs(req.content.decode(), keep_blank_values=True)
        return httpx.Response(200, json={"status": "success"})
    s = ForeTeesSession()
    s.client._transport = httpx.MockTransport(handler)
    submit_booking(
        s, slot=slot, form=slot_form,
        member_id="10326", member_name="Carl", member_user="6605",
        block_other_slots=False,
    )
    s.close()
    assert submitted["player2"] == [""]
    assert submitted["player5"] == [""]


def test_submit_booking_treats_slot_form_response_as_failure(slot, slot_form):
    """If ForeTees returns the slot-form config (no submit happened), we bail."""
    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"show_member_tbd": True, "page_title": "Booking"})
    s = ForeTeesSession()
    s.client._transport = httpx.MockTransport(handler)
    result = submit_booking(
        s, slot=slot, form=slot_form,
        member_id="10326", member_name="Carl", member_user="6605",
    )
    s.close()
    assert not result.success
    assert result.unexpected_response is True


def test_submit_booking_treats_explicit_error_as_failure(slot, slot_form):
    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"error": "slot already taken"})
    s = ForeTeesSession()
    s.client._transport = httpx.MockTransport(handler)
    result = submit_booking(
        s, slot=slot, form=slot_form,
        member_id="10326", member_name="Carl", member_user="6605",
    )
    s.close()
    assert not result.success
    assert "taken" in (result.error_message or "").lower()


def test_submit_booking_treats_empty_json_as_success(slot, slot_form):
    """Real ForeTees often returns an empty/sparse JSON after successful submit
    (the browser navigates away to Member_sheet). Treat that as success."""
    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={})
    s = ForeTeesSession()
    s.client._transport = httpx.MockTransport(handler)
    result = submit_booking(
        s, slot=slot, form=slot_form,
        member_id="10326", member_name="Carl", member_user="6605",
    )
    s.close()
    assert result.success
