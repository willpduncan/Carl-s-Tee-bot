"""Configuration loaded from environment variables (or /etc/teebot/secrets.env)."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv


class MissingEnvError(RuntimeError):
    """Raised when a required environment variable is not set."""


_SECRETS_PATH = Path("/etc/teebot/secrets.env")


def _load_dotenv_if_present() -> None:
    """Load /etc/teebot/secrets.env if it exists. No-op otherwise."""
    if _SECRETS_PATH.exists():
        load_dotenv(_SECRETS_PATH, override=False)


def _required(name: str) -> str:
    val = os.environ.get(name)
    if not val:
        raise MissingEnvError(f"Required environment variable {name} is not set")
    return val


@dataclass(frozen=True)
class Config:
    foretees_username: str
    foretees_password: str = field(repr=False)
    bot_gmail_address: str
    bot_gmail_app_password: str = field(repr=False)
    carl_email: str
    operator_email: str
    timezone: str
    db_path: str

    @classmethod
    def from_env(cls) -> Config:
        _load_dotenv_if_present()
        return cls(
            foretees_username=_required("FORETEES_USERNAME"),
            foretees_password=_required("FORETEES_PASSWORD"),
            bot_gmail_address=_required("BOT_GMAIL_ADDRESS"),
            bot_gmail_app_password=_required("BOT_GMAIL_APP_PASSWORD"),
            carl_email=_required("CARL_EMAIL"),
            operator_email=_required("OPERATOR_EMAIL"),
            timezone=_required("TIMEZONE"),
            db_path=_required("DB_PATH"),
        )
