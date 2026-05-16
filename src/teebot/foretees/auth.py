"""Clubhouse Online + ForeTees SSO login flow."""
from __future__ import annotations

import re
from dataclasses import dataclass

from bs4 import BeautifulSoup

from .session import ForeTeesSession


CLUBHOUSE_LOGIN_URL = "https://pfcc.clubhouseonline-e3.com/login.aspx?ReturnUrl=%2fMember-Central"
MEMBER_CENTRAL_URL = "https://pfcc.clubhouseonline-e3.com/Member-Central"


class AuthError(RuntimeError):
    """Raised when authentication fails."""


@dataclass(frozen=True)
class AuthResult:
    success: bool
    foretees_landing_url: str


def _parse_aspnet_form(html: str) -> dict[str, str]:
    soup = BeautifulSoup(html, "lxml")
    fields = {}
    for inp in soup.find_all("input"):
        name = inp.get("name")
        val = inp.get("value", "")
        if name and inp.get("type", "").lower() == "hidden":
            fields[name] = val
    return fields


def _extract_foretees_link(html: str) -> str:
    """Find the ForeTees launch link on the Member Central page."""
    soup = BeautifulSoup(html, "lxml")
    for a in soup.find_all("a"):
        href = a.get("href", "")
        text = (a.get_text() or "").lower()
        if "foretees" in href.lower() or "foretees" in text or "tee time" in text:
            return href
    raise AuthError("ForeTees launch link not found on Member Central page")


def login(session: ForeTeesSession, *, username: str, password: str) -> AuthResult:
    """Run the full Clubhouse → SSO → ForeTees login chain.

    Returns the URL ForeTees landed us at (after SSO redirect).
    Raises AuthError on any failure.
    """
    # 1. GET the login page to extract viewstate fields
    r = session.client.get(CLUBHOUSE_LOGIN_URL)
    if r.status_code != 200:
        raise AuthError(f"GET login.aspx returned {r.status_code}")
    form_fields = _parse_aspnet_form(r.text)
    if "__VIEWSTATE" not in form_fields:
        raise AuthError("Could not find __VIEWSTATE in login page")

    # 2. POST credentials
    form_fields["ctl00$mainContentPlaceHolder$Login1$UserName"] = username
    form_fields["ctl00$mainContentPlaceHolder$Login1$Password"] = password
    form_fields["ctl00$mainContentPlaceHolder$Login1$LoginButton"] = "Login"

    r = session.client.post(CLUBHOUSE_LOGIN_URL, data=form_fields)
    if "Invalid username or password" in r.text or "login.aspx" in str(r.url).lower():
        raise AuthError("Clubhouse Online login failed (invalid credentials?)")
    if r.status_code != 200:
        raise AuthError(f"After login POST, got status {r.status_code}")

    # 3. Find the ForeTees launch link
    ft_href = _extract_foretees_link(r.text)
    if not ft_href.startswith("http"):
        ft_href = str(r.url.join(ft_href))

    # 4. Follow it (will SSO-redirect to www1.foretees.com)
    r = session.client.get(ft_href)
    if r.status_code != 200:
        raise AuthError(f"ForeTees SSO returned {r.status_code}")
    if "www1.foretees.com" not in str(r.url):
        raise AuthError(f"Expected to land on foretees.com but landed at {r.url}")

    return AuthResult(success=True, foretees_landing_url=str(r.url))
