"""IMAP receiver for the bot's Gmail."""
from __future__ import annotations

import email
import email.policy
import imaplib
import re
from dataclasses import dataclass


@dataclass(frozen=True)
class RawMessage:
    uid: str
    raw: bytes
    sender: str


_FROM_RE = re.compile(r"<([^>]+)>")


def _extract_sender(raw: bytes) -> str:
    msg = email.message_from_bytes(raw, policy=email.policy.default)
    frm = msg.get("From", "")
    m = _FROM_RE.search(frm)
    if m:
        return m.group(1).strip().lower()
    return frm.strip().lower()


class Inbox:
    def __init__(
        self,
        host: str,
        username: str,
        app_password: str,
        sender_allowlist: set[str],
    ):
        self._host = host
        self._user = username
        self._pw = app_password
        self._allowlist = {a.lower() for a in sender_allowlist}
        self._imap: imaplib.IMAP4_SSL | None = None

    def _connect(self) -> imaplib.IMAP4_SSL:
        if self._imap is None:
            self._imap = imaplib.IMAP4_SSL(self._host)
            self._imap.login(self._user, self._pw)
            self._imap.select("INBOX")
        return self._imap

    def fetch_unread(self) -> list[RawMessage]:
        imap = self._connect()
        status, data = imap.search(None, "UNSEEN")
        if status != "OK" or not data or not data[0]:
            return []
        uids = data[0].split()
        out: list[RawMessage] = []
        for uid in uids:
            status, fetched = imap.fetch(uid, "(RFC822)")
            if status != "OK" or not fetched:
                continue
            raw = fetched[0][1]
            sender = _extract_sender(raw)
            if sender not in self._allowlist:
                # Still mark these as seen so we don't reprocess
                imap.store(uid, "+FLAGS", "\\Seen")
                continue
            out.append(RawMessage(uid=uid.decode(), raw=raw, sender=sender))
        return out

    def mark_seen(self, uid: str) -> None:
        imap = self._connect()
        imap.store(uid.encode(), "+FLAGS", "\\Seen")

    def close(self) -> None:
        if self._imap is not None:
            try:
                self._imap.close()
                self._imap.logout()
            finally:
                self._imap = None
