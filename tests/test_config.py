"""Tests for teebot.config."""
import os

import pytest

from teebot.config import Config, MissingEnvError


def test_loads_required_env(monkeypatch):
    monkeypatch.setenv("FORETEES_USERNAME", "Pfifftex")
    monkeypatch.setenv("FORETEES_PASSWORD", "secret")
    monkeypatch.setenv("BOT_GMAIL_ADDRESS", "teebotcarl@gmail.com")
    monkeypatch.setenv("BOT_GMAIL_APP_PASSWORD", "appspecificpw")
    monkeypatch.setenv("CARL_EMAIL", "cpfiffner62@gmail.com")
    monkeypatch.setenv("OPERATOR_EMAIL", "willpduncan@gmail.com")
    monkeypatch.setenv("TIMEZONE", "America/Chicago")
    monkeypatch.setenv("DB_PATH", "/tmp/teebot.db")
    monkeypatch.setenv("SENDGRID_API_KEY", "SG.test")

    cfg = Config.from_env()
    assert cfg.foretees_username == "Pfifftex"
    assert cfg.foretees_password == "secret"
    assert cfg.bot_gmail_address == "teebotcarl@gmail.com"
    assert cfg.carl_email == "cpfiffner62@gmail.com"
    assert cfg.operator_email == "willpduncan@gmail.com"
    assert cfg.timezone == "America/Chicago"
    assert cfg.sendgrid_api_key == "SG.test"


def test_missing_env_raises(monkeypatch):
    # Clear everything
    for key in ("FORETEES_USERNAME", "FORETEES_PASSWORD"):
        monkeypatch.delenv(key, raising=False)

    with pytest.raises(MissingEnvError) as exc:
        Config.from_env()
    assert "FORETEES_USERNAME" in str(exc.value)


def test_password_not_in_repr(monkeypatch):
    monkeypatch.setenv("FORETEES_USERNAME", "Pfifftex")
    monkeypatch.setenv("FORETEES_PASSWORD", "supersecret123")
    monkeypatch.setenv("BOT_GMAIL_ADDRESS", "x@y.com")
    monkeypatch.setenv("BOT_GMAIL_APP_PASSWORD", "appsecret")
    monkeypatch.setenv("CARL_EMAIL", "x@y.com")
    monkeypatch.setenv("OPERATOR_EMAIL", "x@y.com")
    monkeypatch.setenv("TIMEZONE", "America/Chicago")
    monkeypatch.setenv("DB_PATH", "/tmp/teebot.db")
    monkeypatch.setenv("SENDGRID_API_KEY", "SG.sendgrid-secret")

    cfg = Config.from_env()
    r = repr(cfg)
    assert "supersecret123" not in r
    assert "appsecret" not in r
    assert "SG.sendgrid-secret" not in r
