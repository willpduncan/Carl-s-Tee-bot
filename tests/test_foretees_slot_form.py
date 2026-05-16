"""Tests for slot-form fetch and id_list/id_hash extraction."""
from pathlib import Path

import pytest

from teebot.foretees.slot_form import SlotFormData, parse_slot_form

FIXTURE = Path(__file__).parent / "fixtures" / "slot_form_sample.html"


def test_parse_extracts_id_list_and_hash():
    html = FIXTURE.read_text()
    data = parse_slot_form(html)
    assert isinstance(data, SlotFormData)
    assert data.id_list  # not empty
    assert data.id_hash  # not empty


def test_parse_extracts_callback_map():
    html = FIXTURE.read_text()
    data = parse_slot_form(html)
    # The callback_map should have the slot's core fields
    assert "ttdata" in data.callback_map
    assert "date" in data.callback_map
    assert "course" in data.callback_map
    assert "time:0" in data.callback_map
