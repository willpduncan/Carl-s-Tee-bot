"""Tests for tee-sheet HTML parsing."""
from datetime import date
from pathlib import Path

import pytest

from teebot.foretees.tee_sheet import Slot, parse_tee_sheet

FIXTURE = Path(__file__).parent / "fixtures" / "tee_sheet_sample.html"


def test_parse_returns_slots():
    html = FIXTURE.read_text()
    slots = parse_tee_sheet(html)
    assert len(slots) > 0
    for s in slots:
        assert isinstance(s, Slot)
        assert s.ttdata  # every parsed slot has a ttdata token
        assert s.time and ":" in s.time
        assert s.course
        assert s.index is not None


def test_slots_have_consistent_field_shape():
    html = FIXTURE.read_text()
    slots = parse_tee_sheet(html)
    for s in slots:
        assert hasattr(s, "time")
        assert hasattr(s, "course")
        assert hasattr(s, "ttdata")
        assert hasattr(s, "index")
        assert hasattr(s, "day_of_week")
        assert hasattr(s, "available")


def test_at_least_some_slots_are_available():
    html = FIXTURE.read_text()
    slots = parse_tee_sheet(html)
    assert any(s.available for s in slots)
