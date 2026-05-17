"""Tests for the booking submitter."""
from unittest.mock import MagicMock

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
        callback_map={
            "lstate": "0", "newreq": "yes", "displayOpt": "0",
            "showAvail": "-1", "ttdata": "TOKEN123",
            "date": "20260524", "index": "5",
            "course": "Green to Gold", "returnCourse": "-ALL-",
            "p5": "Yes", "time:0": "9:08 AM", "day": "Sunday",
            "contimes": "1", "s_c": "pfcc", "s_a": "0", "s_m": "56",
            "json_mode": "true",
        },
        raw_html="",
    )


def test_submit_booking_success(slot, slot_form):
    from urllib.parse import parse_qs
    submitted: dict[str, list[str]] = {}
    def handler(req: httpx.Request) -> httpx.Response:
        nonlocal submitted
        submitted = parse_qs(req.content.decode(), keep_blank_values=True)
        return httpx.Response(
            200,
            json={"status": "success", "reservation_id": "RES12345"},
        )
    s = ForeTeesSession()
    s.client._transport = httpx.MockTransport(handler)
    result = submit_booking(
        s, slot=slot, form=slot_form,
        member_id="10326", member_name="Carl A Pfiffner", member_user="6605",
    )
    s.close()
    assert result.success
    assert result.reservation_id == "RES12345"
    # Validate critical fields submitted (multi-value: 5 entries per player field)
    assert submitted.get("ttdata") == ["TOKEN123"]
    assert submitted.get("player_a") == ["Carl A Pfiffner", "", "", "", ""]
    assert submitted.get("user_a") == ["6605", "", "", "", ""]
    assert submitted.get("pcw_a") == ["CRT", "", "", "", ""]
    assert submitted.get("id_list") == ["ID_LIST_VAL"]
    assert submitted.get("id_hash") == ["ID_HASH_VAL"]


def test_submit_booking_slot_taken(slot, slot_form):
    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"status": "error", "error": "slot already taken"})
    s = ForeTeesSession()
    s.client._transport = httpx.MockTransport(handler)
    result = submit_booking(
        s, slot=slot, form=slot_form,
        member_id="10326", member_name="Carl A Pfiffner", member_user="6605",
    )
    s.close()
    assert not result.success
    assert "taken" in (result.error_message or "").lower()


def test_submit_booking_unexpected_response(slot, slot_form):
    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="<html>blank</html>", headers={"content-type": "text/html"})
    s = ForeTeesSession()
    s.client._transport = httpx.MockTransport(handler)
    result = submit_booking(
        s, slot=slot, form=slot_form,
        member_id="10326", member_name="Carl A Pfiffner", member_user="6605",
    )
    s.close()
    assert not result.success
    assert result.unexpected_response is True
