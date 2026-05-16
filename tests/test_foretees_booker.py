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
    submitted_body = {}
    def handler(req: httpx.Request) -> httpx.Response:
        body = req.content.decode()
        for kv in body.split("&"):
            if "=" in kv:
                k, v = kv.split("=", 1)
                submitted_body[k] = v
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
    # Validate that critical fields were submitted
    assert submitted_body.get("ttdata") == "TOKEN123"
    assert "player_a" in submitted_body
    assert "user_a" in submitted_body
    assert submitted_body.get("pcw_a") == "CRT"
    assert submitted_body.get("p9_a") == "18"
    assert submitted_body.get("id_list") == "ID_LIST_VAL"
    assert submitted_body.get("id_hash") == "ID_HASH_VAL"


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
