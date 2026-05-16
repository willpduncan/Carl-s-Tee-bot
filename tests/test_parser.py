"""Tests for email-request parser."""
from datetime import date
from pathlib import Path

import pytest

from teebot.parser import (
    ParsedRequest,
    ParseError,
    parse_request_email,
    parse_cancel,
)

FIXTURES = Path(__file__).parent / "fixtures" / "emails"


def _load(name: str) -> bytes:
    return (FIXTURES / name).read_bytes()


def test_parse_structured_email():
    req = parse_request_email(_load("valid_structured.eml"), today=date(2026, 5, 15))
    assert req.target_date == date(2026, 5, 24)
    assert req.course == "Green"
    assert req.window_start == "08:00"
    assert req.window_end == "10:00"
    assert req.preferred_time == "09:00"


def test_parse_freeform_email():
    req = parse_request_email(_load("valid_freeform.eml"), today=date(2026, 5, 15))
    assert req.target_date == date(2026, 5, 24)
    assert req.course == "Green"
    assert req.window_start == "08:00"
    assert req.window_end == "10:00"
    assert req.preferred_time == "09:00"


def test_parse_malformed_raises():
    with pytest.raises(ParseError) as exc:
        parse_request_email(_load("malformed.eml"), today=date(2026, 5, 15))
    assert "course" in str(exc.value).lower() or "time" in str(exc.value).lower()


def test_thursday_restriction_green_or_gold():
    body = b"""From: x@y.com
To: z@y.com
Subject: tee time

Thursday May 28, Green, 9-11 AM, prefer 10
"""
    req = parse_request_email(body, today=date(2026, 5, 15))
    assert req.target_date == date(2026, 5, 28)
    assert req.course == "Green"  # Green allowed on Thursday


def test_thursday_white_rejected():
    body = b"""From: x@y.com
To: z@y.com
Subject: tee time

Thursday May 28, White, 9-11 AM, prefer 10
"""
    with pytest.raises(ParseError) as exc:
        parse_request_email(body, today=date(2026, 5, 15))
    assert "thursday" in str(exc.value).lower() or "white" in str(exc.value).lower()


def test_preferred_outside_window_rejected():
    body = b"""From: x@y.com
To: z@y.com
Subject: tee time

Sunday May 24, Green, 8-10 AM, prefer 11 AM
"""
    with pytest.raises(ParseError):
        parse_request_email(body, today=date(2026, 5, 15))


def test_default_preferred_to_midpoint_when_missing():
    body = b"""From: x@y.com
To: z@y.com
Subject: tee time

Sunday May 24, Green, 8-10 AM
"""
    req = parse_request_email(body, today=date(2026, 5, 15))
    assert req.preferred_time == "09:00"


def test_window_more_than_7_days_out_rejected():
    body = b"""From: x@y.com
To: z@y.com
Subject: tee time

Friday June 5, Green, 8-10 AM, prefer 9
"""
    with pytest.raises(ParseError) as exc:
        parse_request_email(body, today=date(2026, 5, 15))
    assert "7 days" in str(exc.value) or "future" in str(exc.value).lower()


def test_parse_cancel():
    body = b"""From: x@y.com
To: z@y.com
Subject: Re: tee time

cancel
"""
    assert parse_cancel(body) is True


def test_parse_cancel_with_extra_text():
    body = b"""From: x@y.com
To: z@y.com
Subject: Re: tee time

CANCEL please

Thanks - Carl
"""
    assert parse_cancel(body) is True


def test_parse_cancel_returns_false_for_other():
    body = b"""From: x@y.com
To: z@y.com
Subject: Re: tee time

Sunday May 24, Green, 9-10 AM
"""
    assert parse_cancel(body) is False
