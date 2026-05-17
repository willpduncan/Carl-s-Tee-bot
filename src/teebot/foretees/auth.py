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


def _find_login_field_names(html: str) -> dict[str, str]:
    """Discover the actual username/password/login-button field names.

    Pine Forest's Clubhouse Online uses Kentico CMS with verbose compound
    field names that vary by widget config. We match by suffix.
    """
    soup = BeautifulSoup(html, "lxml")
    out: dict[str, str] = {}
    for inp in soup.find_all("input"):
        name = inp.get("name", "")
        if not name:
            continue
        if name.endswith("$UserName"):
            out["username"] = name
        elif name.endswith("$Password"):
            out["password"] = name
        elif name.endswith("$LoginButton"):
            out["login_button"] = name
    return out


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

    # 2. Discover the actual login field names + POST credentials
    field_names = _find_login_field_names(r.text)
    missing = {"username", "password", "login_button"} - field_names.keys()
    if missing:
        raise AuthError(
            f"Could not find login form fields {missing} on login.aspx"
        )
    form_fields[field_names["username"]] = username
    form_fields[field_names["password"]] = password
    form_fields[field_names["login_button"]] = "Login"

    r = session.client.post(CLUBHOUSE_LOGIN_URL, data=form_fields)

    import logging
    _log = logging.getLogger("teebot.auth")
    _log.info(
        "Login POST result: status=%s final_url=%s body_snippet=%r",
        r.status_code, str(r.url), r.text[:500],
    )

    if "Invalid username or password" in r.text or "login.aspx" in str(r.url).lower():
        raise AuthError("Clubhouse Online login failed (invalid credentials?)")
    if r.status_code != 200:
        raise AuthError(f"After login POST, got status {r.status_code}")

    # 3. Find the ForeTees launch link
    ft_href = _extract_foretees_link(r.text)
    if not ft_href.startswith("http"):
        ft_href = str(r.url.join(ft_href))

    # 4. GET the SSO bridge page (Clubhouse Online side)
    r = session.client.get(ft_href)
    if r.status_code != 200:
        raise AuthError(f"ForeTees SSO bridge returned {r.status_code}")

    # 5. If we already landed on ForeTees, we're done
    if "www1.foretees.com" in str(r.url):
        return AuthResult(success=True, foretees_landing_url=str(r.url))

    # 6. Otherwise this is a Clubhouse page with an auto-submit form that
    #    POSTs SSO tokens to ForeTees. Parse the form, submit it ourselves.
    soup = BeautifulSoup(r.text, "lxml")
    form = soup.find("form")
    if form is None:
        raise AuthError(
            f"SSO bridge has no <form> to submit (landed at {r.url})"
        )
    action = form.get("action", "")
    if not action:
        raise AuthError("SSO bridge form has no action URL")
    if not action.startswith("http"):
        action = str(r.url.join(action))

    sso_fields: dict[str, str] = {}
    for inp in form.find_all("input"):
        name = inp.get("name")
        if name:
            sso_fields[name] = inp.get("value", "")

    _log.info(
        "Submitting SSO form: action=%s field_count=%d",
        action, len(sso_fields),
    )
    r = session.client.post(action, data=sso_fields)
    if r.status_code != 200:
        raise AuthError(f"ForeTees SSO POST returned {r.status_code}")
    if "www1.foretees.com" not in str(r.url):
        raise AuthError(
            f"After SSO POST, expected to land on foretees.com but got {r.url}"
        )

    return AuthResult(success=True, foretees_landing_url=str(r.url))
