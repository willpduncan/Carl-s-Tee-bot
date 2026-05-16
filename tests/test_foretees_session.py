"""Tests for ForeTees session wrapper."""
from unittest.mock import MagicMock

import httpx
import pytest

from teebot.foretees.session import DetectionSignal, ForeTeesSession


def test_session_uses_realistic_user_agent():
    with ForeTeesSession() as s:
        ua = s.client.headers["User-Agent"]
        assert "Chrome" in ua
        assert "Mozilla" in ua
        assert "Safari" in ua


def test_audit_hook_called_on_request():
    audit_calls = []
    def audit(event: str, **kwargs):
        audit_calls.append((event, kwargs))

    s = ForeTeesSession(audit_hook=audit)
    transport = httpx.MockTransport(lambda req: httpx.Response(200, text="ok"))
    s.client._transport = transport
    s.client.get("https://example.com/test")
    s.close()

    assert any(e == "http_request" for e, _ in audit_calls)
    assert any(e == "http_response" for e, _ in audit_calls)


def test_cookies_persist_across_requests():
    s = ForeTeesSession()
    def handler(req: httpx.Request) -> httpx.Response:
        if req.url.path == "/set":
            return httpx.Response(200, headers={"set-cookie": "sid=abc; path=/"})
        return httpx.Response(200, text=req.headers.get("cookie", ""))
    s.client._transport = httpx.MockTransport(handler)
    s.client.get("https://example.com/set")
    r = s.client.get("https://example.com/echo")
    assert "sid=abc" in r.text
    s.close()


def test_datadome_cookie_raises_detection_signal():
    s = ForeTeesSession()
    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(200, headers={"set-cookie": "datadome=BLOCKED123; path=/"})
    s.client._transport = httpx.MockTransport(handler)
    with pytest.raises(DetectionSignal) as exc:
        s.client.get("https://www1.foretees.com/test")
    assert "datadome" in str(exc.value).lower()
    s.close()


def test_403_raises_detection_signal():
    s = ForeTeesSession()
    s.client._transport = httpx.MockTransport(lambda req: httpx.Response(403, text="forbidden"))
    with pytest.raises(DetectionSignal) as exc:
        s.client.get("https://www1.foretees.com/test")
    assert "403" in str(exc.value)
    s.close()


def test_429_raises_detection_signal():
    s = ForeTeesSession()
    s.client._transport = httpx.MockTransport(lambda req: httpx.Response(429, text="rate limited"))
    with pytest.raises(DetectionSignal):
        s.client.get("https://www1.foretees.com/test")
    s.close()


def test_captcha_in_body_raises_detection_signal():
    s = ForeTeesSession()
    s.client._transport = httpx.MockTransport(
        lambda req: httpx.Response(
            200,
            headers={"content-type": "text/html"},
            text="<html>Please complete the captcha verification</html>",
        )
    )
    with pytest.raises(DetectionSignal) as exc:
        s.client.get("https://www1.foretees.com/test")
    assert "captcha" in str(exc.value).lower() or "verification" in str(exc.value).lower()
    s.close()
