"""Wraps httpx.Client with realistic browser headers, audit hooks, and
inline bot-detection checks that raise DetectionSignal on any tripwire."""
from __future__ import annotations

import time
from typing import Callable

import httpx


class DetectionSignal(RuntimeError):
    """Raised when a response indicates we've been flagged as a bot.

    Triggers (any one of):
      - response sets a `datadome` cookie
      - response status is 401, 403, or 429
      - response body contains 'captcha' or 'verification' keyword
    """


# Realistic Chrome on macOS UA — picked from the actual HAR
_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/132.0.0.0 Safari/537.36"
)

_DEFAULT_HEADERS = {
    "User-Agent": _USER_AGENT,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Cache-Control": "max-age=0",
    "Sec-Fetch-Site": "same-origin",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-User": "?1",
    "Sec-Fetch-Dest": "document",
    "Upgrade-Insecure-Requests": "1",
}


AuditHook = Callable[..., None]


_DETECTION_STATUS_CODES = (401, 403, 429)
_DETECTION_BODY_PATTERNS = ("captcha", "verification challenge", "please verify")


def _has_datadome_cookie(response: httpx.Response) -> bool:
    for value in response.headers.get_list("set-cookie"):
        if "datadome" in value.lower():
            return True
    return False


class ForeTeesSession:
    """Reusable httpx.Client with cookie persistence, audit hooks, and
    inline bot-detection checks that raise DetectionSignal."""

    def __init__(self, audit_hook: AuditHook | None = None, timeout: float = 30.0):
        self._audit = audit_hook or (lambda *a, **kw: None)
        self.client = httpx.Client(
            headers=_DEFAULT_HEADERS,
            timeout=httpx.Timeout(timeout),
            follow_redirects=True,
        )
        self.client.event_hooks = {
            "request": [self._on_request],
            "response": [self._on_response],
        }

    def _on_request(self, request: httpx.Request) -> None:
        request.extensions["t0"] = time.monotonic_ns()
        self._audit(
            "http_request",
            method=request.method,
            url=str(request.url),
        )

    def _on_response(self, response: httpx.Response) -> None:
        t0 = response.request.extensions.get("t0")
        elapsed_ms = (time.monotonic_ns() - t0) // 1_000_000 if t0 else None
        self._audit(
            "http_response",
            method=response.request.method,
            url=str(response.request.url),
            status=response.status_code,
            elapsed_ms=elapsed_ms,
        )
        # Detection checks
        if _has_datadome_cookie(response):
            raise DetectionSignal(
                f"datadome cookie set by {response.request.url}"
            )
        if response.status_code in _DETECTION_STATUS_CODES:
            raise DetectionSignal(
                f"HTTP {response.status_code} from {response.request.url}"
            )
        # Body keyword check — only on HTML responses
        ctype = response.headers.get("content-type", "").lower()
        if "html" in ctype:
            response.read()  # ensure body is loaded
            body_lower = response.text.lower()
            for pat in _DETECTION_BODY_PATTERNS:
                if pat in body_lower:
                    raise DetectionSignal(
                        f"detection keyword '{pat}' in response body from {response.request.url}"
                    )

    def close(self) -> None:
        self.client.close()

    def __enter__(self) -> ForeTeesSession:
        return self

    def __exit__(self, *args) -> None:
        self.close()
