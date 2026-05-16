"""Tests for the Clubhouse Online → ForeTees auth chain.

We mock httpx transport responses so we don't hit the real site.
"""
from unittest.mock import patch

import httpx
import pytest

from teebot.foretees.auth import AuthError, login
from teebot.foretees.session import ForeTeesSession


_LOGIN_PAGE_HTML = """
<html><body>
<form id="aspnetForm" method="post" action="./login.aspx?ReturnUrl=%2fMember-Central">
<input type="hidden" name="__VIEWSTATE" value="VSTATE_VAL" />
<input type="hidden" name="__EVENTVALIDATION" value="EVAL_VAL" />
<input type="text" name="ctl00$mainContentPlaceHolder$Login1$UserName" />
<input type="password" name="ctl00$mainContentPlaceHolder$Login1$Password" />
<input type="submit" name="ctl00$mainContentPlaceHolder$Login1$LoginButton" value="Login" />
</form>
</body></html>
"""


_MEMBER_CENTRAL_HTML = """
<html><body>
<a id="foretees-launch" href="/foretees/launch.aspx?token=ABC123">ForeTees</a>
</body></html>
"""


def _handler(req: httpx.Request) -> httpx.Response:
    if req.url.path == "/login.aspx" and req.method == "GET":
        return httpx.Response(200, headers={"content-type": "text/html"}, text=_LOGIN_PAGE_HTML)
    if req.url.path == "/login.aspx" and req.method == "POST":
        return httpx.Response(
            302,
            headers={"location": "/Member-Central"},
        )
    if req.url.path == "/Member-Central":
        return httpx.Response(200, headers={"content-type": "text/html"}, text=_MEMBER_CENTRAL_HTML)
    if req.url.path == "/foretees/launch.aspx":
        return httpx.Response(
            302,
            headers={"location": "https://www1.foretees.com/v5/pfcc_golf_m56/Member_announce"},
        )
    if req.url.host == "www1.foretees.com":
        return httpx.Response(200, headers={"content-type": "text/html"}, text="<html>Welcome</html>")
    return httpx.Response(404)


def test_login_succeeds_against_mocked_flow():
    s = ForeTeesSession()
    s.client._transport = httpx.MockTransport(_handler)
    result = login(s, username="Pfifftex", password="secret")
    assert result.success
    assert "foretees" in result.foretees_landing_url.lower()
    s.close()


def test_login_raises_on_bad_credentials():
    def bad_handler(req: httpx.Request) -> httpx.Response:
        if req.url.path == "/login.aspx" and req.method == "GET":
            return httpx.Response(200, headers={"content-type": "text/html"}, text=_LOGIN_PAGE_HTML)
        if req.url.path == "/login.aspx" and req.method == "POST":
            # Returning the login page again signals failed auth
            return httpx.Response(
                200,
                headers={"content-type": "text/html"},
                text=_LOGIN_PAGE_HTML + " Invalid username or password.",
            )
        return httpx.Response(404)
    s = ForeTeesSession()
    s.client._transport = httpx.MockTransport(bad_handler)
    with pytest.raises(AuthError) as exc:
        login(s, username="Pfifftex", password="wrong")
    assert "auth" in str(exc.value).lower() or "login" in str(exc.value).lower()
    s.close()
