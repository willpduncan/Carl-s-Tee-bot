# TeeBot Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a single-user automated ForeTees tee-time booking bot for Carl Pfiffner at Pine Forest Country Club, triggered by emails from Carl, firing at 8:00 AM Central daily.

**Architecture:** Three Python processes on a Linux VPS — (1) IMAP email poller that ingests Carl's weekly preferences via Gmail, (2) HTTP-based ForeTees client that authenticates and books slots, (3) systemd-timer cron orchestrator that fires the booker at 7:58 AM Central. SQLite for persistence. Raw HTTP (no browser) for speed, with defensive instrumentation that hard-stops on any bot-detection signal.

**Tech Stack:**
- Python 3.12
- `httpx` (HTTP client with HTTP/2 + connection reuse + good timing instrumentation)
- `beautifulsoup4` + `lxml` (HTML parsing for ForeTees tee-sheet and slot-form pages)
- `python-dotenv` (load `/etc/teebot/secrets.env`)
- Standard library: `sqlite3`, `imaplib`, `smtplib`, `email`, `zoneinfo`, `re`, `logging`, `pathlib`, `dataclasses`
- `pytest` + `pytest-mock` for tests
- Linux VPS (Ubuntu 24.04), `systemd` for service supervision

**Spec reference:** [docs/specs/2026-05-15-foretees-bot-design.md](../specs/2026-05-15-foretees-bot-design.md)

---

## File Structure

```
/Users/willduncan/teebot/
├── .gitignore                                  # already exists
├── README.md                                   # Task 1
├── pyproject.toml                              # Task 1 (Python project metadata + deps)
├── docs/
│   ├── specs/2026-05-15-foretees-bot-design.md # already exists
│   ├── plans/2026-05-15-teebot-implementation.md
│   ├── setup.md                                # Task 17 (deployment guide)
│   └── EMERGENCY.md                            # Task 17 (kill switch + recovery)
├── src/teebot/
│   ├── __init__.py                             # Task 1
│   ├── config.py                               # Task 2 — secrets/env loading
│   ├── db.py                                   # Task 3 — schema + connection helper
│   ├── audit.py                                # Task 4 — audit log helpers
│   ├── parser.py                               # Task 5 — request email parsing
│   ├── mailer.py                               # Task 6 — SMTP sender
│   ├── inbox.py                                # Task 7 — IMAP receiver
│   ├── foretees/
│   │   ├── __init__.py                         # Task 8
│   │   ├── session.py                          # Task 8 — httpx.Client wrapper, cookies
│   │   ├── auth.py                             # Task 9 — Clubhouse + ForeTees login
│   │   ├── tee_sheet.py                        # Task 10 — Member_sheet fetch + parse
│   │   ├── slot_form.py                        # Task 11 — slot-form fetch + extract id_list/id_hash
│   │   └── booker.py                           # Task 12 — booking submit POST
│   ├── booker_orchestrator.py                  # Tasks 13-14 — the 5-phase 8 AM run
│   └── poller_orchestrator.py                  # Task 15 — the 30s IMAP loop
├── scripts/
│   ├── init_db.py                              # Task 3 — one-shot DB init
│   ├── run_booker.py                           # Task 16 — systemd entry point
│   ├── run_poller.py                           # Task 16 — systemd entry point
│   └── kill_switch.sh                          # Task 17 — flip bot_enabled=0
├── systemd/
│   ├── teebot-booker.service                   # Task 16
│   ├── teebot-booker.timer                     # Task 16
│   ├── teebot-poller.service                   # Task 16
│   └── teebot-poller.timer                     # Task 16
└── tests/
    ├── __init__.py
    ├── conftest.py                             # Task 1 — pytest fixtures (tmp db, sample HAR)
    ├── fixtures/
    │   ├── pineforest-capture.har              # Task 1 — copy of HAR for fixtures
    │   ├── tee_sheet_sample.html               # Task 10 — extracted from HAR
    │   ├── slot_form_sample.html               # Task 11 — extracted from HAR
    │   └── emails/
    │       ├── valid_structured.eml            # Task 5
    │       ├── valid_freeform.eml              # Task 5
    │       ├── malformed.eml                   # Task 5
    │       └── partner_reply_names.eml         # Task 15
    ├── test_config.py
    ├── test_db.py
    ├── test_audit.py
    ├── test_parser.py
    ├── test_mailer.py
    ├── test_inbox.py
    ├── test_foretees_session.py
    ├── test_foretees_auth.py
    ├── test_foretees_tee_sheet.py
    ├── test_foretees_slot_form.py
    ├── test_foretees_booker.py
    ├── test_booker_orchestrator.py
    └── test_poller_orchestrator.py
```

**Module responsibilities (one purpose each):**
- `config.py` — load + validate environment variables; no other logic
- `db.py` — DDL, connection factory; no business logic
- `audit.py` — append-only audit row writer; reused by everyone
- `parser.py` — pure functions: email body → `ParsedRequest` dataclass
- `mailer.py` — pure-side-effect: send an email (text body, subject, recipient)
- `inbox.py` — fetch unread messages from bot Gmail via IMAP; no parsing logic
- `foretees/session.py` — wraps `httpx.Client` with cookie jar + audit hooks
- `foretees/auth.py` — login + SSO handoff; produces an authenticated session
- `foretees/tee_sheet.py` — GET Member_sheet, parse out `Slot` records
- `foretees/slot_form.py` — POST Member_slot, extract `id_list`/`id_hash` etc.
- `foretees/booker.py` — POST Member_slot with full submit fields
- `booker_orchestrator.py` — composes auth + tee_sheet + slot_form + booker into the 5-phase race
- `poller_orchestrator.py` — IMAP loop; classifies as new request or partner reply; updates DB

---

# PHASE 1: Foundation (Tasks 1–4)

Produces: a project skeleton with deps installed, a config module that loads secrets, a SQLite schema, and an audit-log helper. End state: `pytest` runs and passes the foundation tests.

---

### Task 1: Project scaffolding + dependencies + test harness

**Files:**
- Create: `/Users/willduncan/teebot/pyproject.toml`
- Create: `/Users/willduncan/teebot/README.md`
- Create: `/Users/willduncan/teebot/src/teebot/__init__.py`
- Create: `/Users/willduncan/teebot/tests/__init__.py`
- Create: `/Users/willduncan/teebot/tests/conftest.py`
- Copy: `/Users/willduncan/Downloads/pineforest-capture.har` → `/Users/willduncan/teebot/tests/fixtures/pineforest-capture.har`

- [ ] **Step 1: Create `pyproject.toml`**

```toml
[project]
name = "teebot"
version = "0.1.0"
description = "Automated ForeTees tee-time booking bot for Pine Forest Country Club"
requires-python = ">=3.12"
dependencies = [
    "httpx>=0.27",
    "beautifulsoup4>=4.12",
    "lxml>=5.0",
    "python-dotenv>=1.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "pytest-mock>=3.12",
]

[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[tool.setuptools.packages.find]
where = ["src"]

[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = ["src"]
```

- [ ] **Step 2: Set up the virtualenv and install deps**

Run:
```bash
cd /Users/willduncan/teebot
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

Expected: clean install, no errors.

- [ ] **Step 3: Create minimal package init files**

`/Users/willduncan/teebot/src/teebot/__init__.py`:
```python
"""TeeBot — automated ForeTees tee-time booking for Pine Forest CC."""
__version__ = "0.1.0"
```

`/Users/willduncan/teebot/tests/__init__.py`: empty file.

- [ ] **Step 4: Create `tests/conftest.py` with shared fixtures**

```python
"""Shared pytest fixtures."""
import sqlite3
from pathlib import Path

import pytest

FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture
def tmp_db(tmp_path):
    """In-memory SQLite connection for tests."""
    db_path = tmp_path / "test.db"
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    yield conn
    conn.close()


@pytest.fixture
def har_path():
    """Path to the recorded HAR file."""
    return FIXTURES_DIR / "pineforest-capture.har"
```

- [ ] **Step 5: Copy the HAR fixture**

Run:
```bash
mkdir -p /Users/willduncan/teebot/tests/fixtures
cp /Users/willduncan/Downloads/pineforest-capture.har /Users/willduncan/teebot/tests/fixtures/
```

Verify: `ls -lh /Users/willduncan/teebot/tests/fixtures/pineforest-capture.har` shows ~9.5 MB file.

- [ ] **Step 6: Write a smoke test**

`/Users/willduncan/teebot/tests/test_smoke.py`:
```python
"""Sanity check that the test harness works."""
from teebot import __version__


def test_version():
    assert __version__ == "0.1.0"


def test_har_fixture_loads(har_path):
    import json
    with open(har_path) as f:
        har = json.load(f)
    assert "log" in har
    assert len(har["log"]["entries"]) > 100  # ~290 entries
```

- [ ] **Step 7: Run the smoke test**

Run: `cd /Users/willduncan/teebot && .venv/bin/pytest tests/test_smoke.py -v`
Expected: 2 tests PASS.

- [ ] **Step 8: Create README.md**

```markdown
# TeeBot

Automated ForeTees tee-time booking bot for Carl Pfiffner at Pine Forest Country Club.

## Quick reference
- Spec: [docs/specs/2026-05-15-foretees-bot-design.md](docs/specs/2026-05-15-foretees-bot-design.md)
- Implementation plan: [docs/plans/2026-05-15-teebot-implementation.md](docs/plans/2026-05-15-teebot-implementation.md)
- Deployment guide: [docs/setup.md](docs/setup.md)
- Emergency runbook: [docs/EMERGENCY.md](docs/EMERGENCY.md)

## Local development
```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
pytest
```
```

- [ ] **Step 9: Commit**

```bash
cd /Users/willduncan/teebot
git add pyproject.toml README.md src/teebot/__init__.py tests/__init__.py tests/conftest.py tests/test_smoke.py tests/fixtures/pineforest-capture.har
git commit -m "$(cat <<'EOF'
chore: project scaffolding, deps, HAR fixture, smoke test

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 2: Config module — env-var loading

**Files:**
- Create: `src/teebot/config.py`
- Create: `tests/test_config.py`

- [ ] **Step 1: Write the failing test**

`tests/test_config.py`:
```python
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

    cfg = Config.from_env()
    assert cfg.foretees_username == "Pfifftex"
    assert cfg.foretees_password == "secret"
    assert cfg.bot_gmail_address == "teebotcarl@gmail.com"
    assert cfg.carl_email == "cpfiffner62@gmail.com"
    assert cfg.operator_email == "willpduncan@gmail.com"
    assert cfg.timezone == "America/Chicago"


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

    cfg = Config.from_env()
    r = repr(cfg)
    assert "supersecret123" not in r
    assert "appsecret" not in r
```

- [ ] **Step 2: Run tests, verify they fail**

Run: `cd /Users/willduncan/teebot && .venv/bin/pytest tests/test_config.py -v`
Expected: ImportError or 3 FAIL.

- [ ] **Step 3: Implement `config.py`**

`src/teebot/config.py`:
```python
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
```

- [ ] **Step 4: Run tests, verify they pass**

Run: `cd /Users/willduncan/teebot && .venv/bin/pytest tests/test_config.py -v`
Expected: 3 PASS.

- [ ] **Step 5: Commit**

```bash
git add src/teebot/config.py tests/test_config.py
git commit -m "feat(config): env-var loading with secrets redaction in repr"
```

---

### Task 3: Database schema + connection helper

**Files:**
- Create: `src/teebot/db.py`
- Create: `scripts/init_db.py`
- Create: `tests/test_db.py`

- [ ] **Step 1: Write failing tests**

`tests/test_db.py`:
```python
"""Tests for db schema + connection helpers."""
import sqlite3
from pathlib import Path

import pytest

from teebot.db import connect, init_schema, REQUIRED_TABLES


def test_init_schema_creates_all_tables(tmp_path):
    db = tmp_path / "t.db"
    conn = connect(str(db))
    init_schema(conn)
    found = {r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    )}
    for t in REQUIRED_TABLES:
        assert t in found
    conn.close()


def test_init_schema_idempotent(tmp_path):
    db = tmp_path / "t.db"
    conn = connect(str(db))
    init_schema(conn)
    init_schema(conn)  # second call should not raise
    conn.close()


def test_config_row_inserted_on_init(tmp_path):
    db = tmp_path / "t.db"
    conn = connect(str(db))
    init_schema(conn)
    row = conn.execute("SELECT bot_enabled, use_browser FROM config WHERE id=1").fetchone()
    assert row[0] == 1   # enabled by default
    assert row[1] == 0   # browser fallback off by default
    conn.close()


def test_requests_unique_pending_per_date(tmp_path):
    db = tmp_path / "t.db"
    conn = connect(str(db))
    init_schema(conn)
    # Insert first pending request
    conn.execute("""
        INSERT INTO requests (target_date, course, preferred_time,
            window_start, window_end, status, created_at, updated_at)
        VALUES ('2026-05-24', 'Green', '09:00', '08:00', '10:00',
            'pending', '2026-05-15 12:00', '2026-05-15 12:00')
    """)
    conn.commit()
    # Insert a SECOND pending request for the same date → should REPLACE first
    conn.execute("""
        INSERT INTO requests (target_date, course, preferred_time,
            window_start, window_end, status, created_at, updated_at)
        VALUES ('2026-05-24', 'Gold', '10:00', '09:00', '11:00',
            'pending', '2026-05-15 13:00', '2026-05-15 13:00')
    """)
    conn.commit()
    rows = list(conn.execute(
        "SELECT course FROM requests WHERE target_date='2026-05-24' AND status='pending'"
    ))
    assert len(rows) == 1
    assert rows[0][0] == "Gold"
    conn.close()


def test_connect_sets_row_factory(tmp_path):
    db = tmp_path / "t.db"
    conn = connect(str(db))
    init_schema(conn)
    conn.execute("""
        INSERT INTO requests (target_date, course, preferred_time,
            window_start, window_end, status, created_at, updated_at)
        VALUES ('2026-05-24', 'Green', '09:00', '08:00', '10:00',
            'pending', '2026-05-15 12:00', '2026-05-15 12:00')
    """)
    conn.commit()
    row = conn.execute("SELECT * FROM requests WHERE target_date='2026-05-24'").fetchone()
    # Row factory should let us access columns by name
    assert row["course"] == "Green"
    conn.close()
```

- [ ] **Step 2: Run, verify they fail**

Run: `.venv/bin/pytest tests/test_db.py -v`
Expected: ImportError on `teebot.db`.

- [ ] **Step 3: Implement `db.py`**

`src/teebot/db.py`:
```python
"""SQLite schema and connection helpers."""
from __future__ import annotations

import sqlite3

REQUIRED_TABLES = ("requests", "bookings", "audit_log", "config")

_DDL = """
CREATE TABLE IF NOT EXISTS requests (
  id              INTEGER PRIMARY KEY AUTOINCREMENT,
  target_date     TEXT NOT NULL,
  course          TEXT NOT NULL,
  preferred_time  TEXT NOT NULL,
  window_start    TEXT NOT NULL,
  window_end      TEXT NOT NULL,
  status          TEXT NOT NULL,
  source_message_id TEXT,
  created_at      TIMESTAMP NOT NULL,
  updated_at      TIMESTAMP NOT NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_requests_pending_per_date
  ON requests(target_date) WHERE status='pending';

CREATE TABLE IF NOT EXISTS bookings (
  id                       INTEGER PRIMARY KEY AUTOINCREMENT,
  request_id               INTEGER NOT NULL REFERENCES requests(id),
  target_date              TEXT NOT NULL,
  booked_time              TEXT,
  course                   TEXT,
  foretees_reservation_id  TEXT,
  partner_status           TEXT NOT NULL DEFAULT 'pending_choice',
  partner_names            TEXT,
  attempt_count            INTEGER NOT NULL DEFAULT 0,
  booking_latency_ms       INTEGER,
  confirmation_message_id  TEXT,
  failure_reason           TEXT,
  created_at               TIMESTAMP NOT NULL
);

CREATE TABLE IF NOT EXISTS audit_log (
  id           INTEGER PRIMARY KEY AUTOINCREMENT,
  timestamp    TIMESTAMP NOT NULL,
  event_type   TEXT NOT NULL,
  request_id   INTEGER REFERENCES requests(id),
  booking_id   INTEGER REFERENCES bookings(id),
  details      TEXT,
  success      BOOLEAN NOT NULL
);

CREATE TABLE IF NOT EXISTS config (
  id            INTEGER PRIMARY KEY CHECK (id = 1),
  bot_enabled   BOOLEAN NOT NULL DEFAULT 1,
  use_browser   BOOLEAN NOT NULL DEFAULT 0,
  last_poll_at  TIMESTAMP
);
"""

_SEED_CONFIG = """
INSERT OR IGNORE INTO config (id, bot_enabled, use_browser)
  VALUES (1, 1, 0);
"""


def connect(db_path: str) -> sqlite3.Connection:
    """Open a SQLite connection with row_factory set to sqlite3.Row."""
    conn = sqlite3.connect(db_path, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


def init_schema(conn: sqlite3.Connection) -> None:
    """Idempotently create tables and seed the config row."""
    conn.executescript(_DDL)
    conn.execute(_SEED_CONFIG)
```

Note: the unique-pending-per-date constraint is a partial index (not the `UNIQUE(target_date, status)` from the spec) — partial indexes are the correct SQLite mechanism. New pending inserts for an existing pending target_date must be handled by application code (DELETE existing pending row, then INSERT) — see Task 7.

- [ ] **Step 4: Update the upsert test to match the actual mechanism**

Edit `tests/test_db.py`, replace `test_requests_unique_pending_per_date` with:

```python
def test_pending_per_date_constraint(tmp_path):
    """Two pending rows for the same date should fail (caller must handle upsert in app code)."""
    db = tmp_path / "t.db"
    conn = connect(str(db))
    init_schema(conn)
    conn.execute("""
        INSERT INTO requests (target_date, course, preferred_time,
            window_start, window_end, status, created_at, updated_at)
        VALUES ('2026-05-24', 'Green', '09:00', '08:00', '10:00',
            'pending', '2026-05-15 12:00', '2026-05-15 12:00')
    """)
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("""
            INSERT INTO requests (target_date, course, preferred_time,
                window_start, window_end, status, created_at, updated_at)
            VALUES ('2026-05-24', 'Gold', '10:00', '09:00', '11:00',
                'pending', '2026-05-15 13:00', '2026-05-15 13:00')
        """)
    # But inserting a non-pending row should work
    conn.execute("""
        INSERT INTO requests (target_date, course, preferred_time,
            window_start, window_end, status, created_at, updated_at)
        VALUES ('2026-05-24', 'Gold', '10:00', '09:00', '11:00',
            'succeeded', '2026-05-15 13:00', '2026-05-15 13:00')
    """)
    conn.close()
```

- [ ] **Step 5: Run, verify all tests pass**

Run: `.venv/bin/pytest tests/test_db.py -v`
Expected: 5 PASS.

- [ ] **Step 6: Create `scripts/init_db.py`**

`scripts/init_db.py`:
```python
"""Idempotently initialize the teebot SQLite database."""
import sys

from teebot.config import Config
from teebot.db import connect, init_schema


def main() -> int:
    cfg = Config.from_env()
    conn = connect(cfg.db_path)
    try:
        init_schema(conn)
        print(f"Initialized schema at {cfg.db_path}")
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 7: Commit**

```bash
git add src/teebot/db.py scripts/init_db.py tests/test_db.py
git commit -m "feat(db): SQLite schema + connection helpers; init_db script"
```

---

### Task 4: Audit log helpers

**Files:**
- Create: `src/teebot/audit.py`
- Create: `tests/test_audit.py`

- [ ] **Step 1: Write failing tests**

`tests/test_audit.py`:
```python
"""Tests for audit log writer."""
import json

import pytest

from teebot.audit import log_event
from teebot.db import connect, init_schema


@pytest.fixture
def conn(tmp_path):
    c = connect(str(tmp_path / "t.db"))
    init_schema(c)
    yield c
    c.close()


def test_log_event_writes_row(conn):
    log_event(conn, "test_event", success=True, details={"foo": "bar"})
    row = conn.execute("SELECT * FROM audit_log").fetchone()
    assert row["event_type"] == "test_event"
    assert row["success"] == 1
    assert json.loads(row["details"]) == {"foo": "bar"}


def test_log_event_with_no_details(conn):
    log_event(conn, "no_details", success=True)
    row = conn.execute("SELECT * FROM audit_log").fetchone()
    assert row["details"] is None


def test_log_event_with_request_and_booking_id(conn):
    # Make a request row first so the FK is satisfied
    conn.execute("""
        INSERT INTO requests (id, target_date, course, preferred_time,
            window_start, window_end, status, created_at, updated_at)
        VALUES (1, '2026-05-24', 'Green', '09:00', '08:00', '10:00',
            'pending', '2026-05-15 12:00', '2026-05-15 12:00')
    """)
    log_event(conn, "request_received", request_id=1, success=True)
    row = conn.execute("SELECT request_id FROM audit_log").fetchone()
    assert row["request_id"] == 1


def test_log_event_failure_serializes_exception(conn):
    log_event(
        conn,
        "login_failed",
        success=False,
        details={"error": "connection refused", "status": 0}
    )
    row = conn.execute("SELECT * FROM audit_log").fetchone()
    assert row["success"] == 0
    payload = json.loads(row["details"])
    assert payload["error"] == "connection refused"
```

- [ ] **Step 2: Run, verify failure**

Run: `.venv/bin/pytest tests/test_audit.py -v`
Expected: ImportError.

- [ ] **Step 3: Implement `audit.py`**

`src/teebot/audit.py`:
```python
"""Append-only audit log writer."""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from typing import Any


def log_event(
    conn: sqlite3.Connection,
    event_type: str,
    *,
    success: bool,
    request_id: int | None = None,
    booking_id: int | None = None,
    details: dict[str, Any] | None = None,
) -> None:
    """Append a row to audit_log. Never raises; failures are swallowed
    because the audit log must not break the main flow."""
    try:
        conn.execute(
            """INSERT INTO audit_log
                 (timestamp, event_type, request_id, booking_id, details, success)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (
                datetime.now(timezone.utc).isoformat(),
                event_type,
                request_id,
                booking_id,
                json.dumps(details) if details is not None else None,
                1 if success else 0,
            ),
        )
    except sqlite3.Error:
        # Audit failures should never break the caller; will be visible in journalctl
        import logging
        logging.exception("Failed to write audit log row")
```

- [ ] **Step 4: Run, verify all pass**

Run: `.venv/bin/pytest tests/test_audit.py -v`
Expected: 4 PASS.

- [ ] **Step 5: Commit**

```bash
git add src/teebot/audit.py tests/test_audit.py
git commit -m "feat(audit): append-only audit log writer"
```

---

# PHASE 2: Email I/O (Tasks 5–7)

Produces: parser turns email bodies into structured requests; mailer sends emails via Gmail SMTP; inbox fetches unread mail via Gmail IMAP. End state: a CLI demo can echo a parsed email back to the sender.

---

### Task 5: Email request parser

**Files:**
- Create: `src/teebot/parser.py`
- Create: `tests/test_parser.py`
- Create: `tests/fixtures/emails/valid_structured.eml`, `valid_freeform.eml`, `malformed.eml`

The parser must handle structured input (labeled fields) AND informal free-text. Time zone is Pine Forest local (America/Chicago). Dates must resolve to specific calendar dates in the next 7 days.

- [ ] **Step 1: Create fixture emails**

`tests/fixtures/emails/valid_structured.eml`:
```
From: cpfiffner62@gmail.com
To: teebotcarl@gmail.com
Subject: tee time
Date: Fri, 15 May 2026 12:00:00 -0500
Message-ID: <abc123@gmail.com>

Day: Sunday May 24
Course: Green
Window: 8:00 AM to 10:00 AM
Preferred: 9:00 AM
```

`tests/fixtures/emails/valid_freeform.eml`:
```
From: cpfiffner62@gmail.com
To: teebotcarl@gmail.com
Subject: tee time
Date: Fri, 15 May 2026 12:00:00 -0500
Message-ID: <def456@gmail.com>

Hey, please book Sunday Green between 8 and 10, ideally 9 AM.
Thanks - Carl
```

`tests/fixtures/emails/malformed.eml`:
```
From: cpfiffner62@gmail.com
To: teebotcarl@gmail.com
Subject: hi
Date: Fri, 15 May 2026 12:00:00 -0500
Message-ID: <ghi789@gmail.com>

hello can I have a tee time
```

- [ ] **Step 2: Write the failing tests**

`tests/test_parser.py`:
```python
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
```

- [ ] **Step 3: Run, verify failure**

Run: `.venv/bin/pytest tests/test_parser.py -v`
Expected: ImportError.

- [ ] **Step 4: Implement `parser.py`**

`src/teebot/parser.py`:
```python
"""Parse Carl's email requests into ParsedRequest dataclasses.

The parser is intentionally lenient — it accepts structured "Day: ..."
labels OR free-text "Sunday, Green, 8-10 AM, prefer 9". It rejects only
emails that are missing required fields or contain contradictions.
"""
from __future__ import annotations

import email
import email.policy
import re
from dataclasses import dataclass
from datetime import date, timedelta
from email.message import EmailMessage


class ParseError(ValueError):
    """Raised when a request email cannot be unambiguously parsed."""


@dataclass(frozen=True)
class ParsedRequest:
    target_date: date
    course: str            # 'Green' | 'Gold' | 'White'
    preferred_time: str    # 'HH:MM' (24-hour)
    window_start: str
    window_end: str
    source_message_id: str | None


_COURSES = ("green", "gold", "white")
_DAY_NAMES = (
    "monday", "tuesday", "wednesday", "thursday",
    "friday", "saturday", "sunday",
)
_MONTH_NAMES = (
    "january", "february", "march", "april", "may", "june",
    "july", "august", "september", "october", "november", "december",
)


def _msg_body(raw: bytes) -> tuple[str, str | None]:
    """Return (lowercased plain-text body, message-id)."""
    msg = email.message_from_bytes(raw, policy=email.policy.default)
    msg_id = msg.get("Message-ID")
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() == "text/plain":
                body = part.get_content()
                break
        else:
            body = msg.get_content()
    else:
        body = msg.get_content()
    return body.lower(), msg_id


def parse_cancel(raw: bytes) -> bool:
    """True iff the email body's first non-empty line is 'cancel'."""
    body, _ = _msg_body(raw)
    for line in body.splitlines():
        s = line.strip()
        if s:
            return s.split()[0] == "cancel"
    return False


def _extract_course(text: str) -> str:
    found = [c for c in _COURSES if re.search(rf"\b{c}\b", text)]
    if not found:
        raise ParseError("course not found (expected Green, Gold, or White)")
    if len(set(found)) > 1:
        raise ParseError(f"multiple courses mentioned: {found}")
    return found[0].capitalize()


def _extract_target_date(text: str, today: date) -> date:
    """Find a date reference in the text and resolve it to a specific date.

    Accepts:
      - 'Sunday' / 'Sun' (next occurrence)
      - 'Sunday May 24' / 'May 24' / '5/24'
      - 'Thursday May 28'
    """
    # Try absolute "<Month> <day>" first
    months_re = "|".join(_MONTH_NAMES)
    m = re.search(rf"\b({months_re})\s+(\d{{1,2}})\b", text)
    if m:
        mon = _MONTH_NAMES.index(m.group(1)) + 1
        day = int(m.group(2))
        try:
            cand = date(today.year, mon, day)
            if cand < today:
                cand = date(today.year + 1, mon, day)
        except ValueError:
            raise ParseError(f"invalid month/day: {m.group(0)}")
        return cand
    # Try "M/D" e.g. "5/24"
    m = re.search(r"\b(\d{1,2})/(\d{1,2})\b", text)
    if m:
        mon, day = int(m.group(1)), int(m.group(2))
        try:
            cand = date(today.year, mon, day)
            if cand < today:
                cand = date(today.year + 1, mon, day)
        except ValueError:
            raise ParseError(f"invalid date: {m.group(0)}")
        return cand
    # Fall back to day-of-week → next occurrence
    for dow_idx, dow in enumerate(_DAY_NAMES):
        if re.search(rf"\b{dow}\b", text) or re.search(rf"\b{dow[:3]}\b", text):
            days_ahead = (dow_idx - today.weekday()) % 7
            if days_ahead == 0:
                days_ahead = 7
            return today + timedelta(days=days_ahead)
    raise ParseError("no date/day-of-week reference found")


_TIME_RE = re.compile(r"(\d{1,2})(?::(\d{2}))?\s*(am|pm)?", re.IGNORECASE)


def _parse_time(token: str) -> str:
    m = _TIME_RE.fullmatch(token.strip())
    if not m:
        raise ParseError(f"unrecognized time: {token!r}")
    hour = int(m.group(1))
    minute = int(m.group(2)) if m.group(2) else 0
    ampm = (m.group(3) or "").lower()
    if ampm == "pm" and hour != 12:
        hour += 12
    elif ampm == "am" and hour == 12:
        hour = 0
    elif not ampm:
        # Bare number: assume AM for 6-11, PM for 12-5, else AM
        if 1 <= hour <= 5:
            hour += 12
    if not (0 <= hour < 24 and 0 <= minute < 60):
        raise ParseError(f"time out of range: {token!r}")
    return f"{hour:02d}:{minute:02d}"


def _extract_window_and_preferred(text: str) -> tuple[str, str, str | None]:
    # Look for "X to Y", "X-Y", or "between X and Y"
    range_pats = [
        r"window[:\s]+(\d{1,2}(?::\d{2})?\s*(?:am|pm)?)\s*(?:to|-|–|—)\s*(\d{1,2}(?::\d{2})?\s*(?:am|pm)?)",
        r"between\s+(\d{1,2}(?::\d{2})?\s*(?:am|pm)?)\s+and\s+(\d{1,2}(?::\d{2})?\s*(?:am|pm)?)",
        r"(\d{1,2}(?::\d{2})?\s*(?:am|pm)?)\s*(?:to|-|–|—)\s*(\d{1,2}(?::\d{2})?\s*(?:am|pm)?)",
    ]
    start = end = None
    for pat in range_pats:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            start = _parse_time(m.group(1))
            end = _parse_time(m.group(2))
            break
    if start is None:
        raise ParseError("time window (e.g. '8-10 AM' or 'between 8 and 10') not found")
    if start >= end:
        raise ParseError(f"window start {start} must be before end {end}")

    # Look for "prefer X" / "ideally X" / "Preferred: X"
    pref_pats = [
        r"prefer(?:red)?[:\s]+(\d{1,2}(?::\d{2})?\s*(?:am|pm)?)",
        r"ideally\s+(\d{1,2}(?::\d{2})?\s*(?:am|pm)?)",
    ]
    preferred = None
    for pat in pref_pats:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            preferred = _parse_time(m.group(1))
            break
    return start, end, preferred


def parse_request_email(raw: bytes, *, today: date) -> ParsedRequest:
    """Parse a request email, raising ParseError on any ambiguity."""
    body, msg_id = _msg_body(raw)
    course = _extract_course(body)
    target = _extract_target_date(body, today)
    # Reject dates beyond 7 days from today (rolling release window is 5 days; allow a bit of slack)
    if target > today + timedelta(days=7):
        raise ParseError(
            f"target date {target} is more than 7 days in the future"
        )
    if target < today:
        raise ParseError(f"target date {target} is in the past")
    # Thursday: only Green or Gold allowed
    if target.weekday() == 3 and course == "White":
        raise ParseError("Thursdays at Pine Forest do not allow White course")

    start, end, preferred = _extract_window_and_preferred(body)
    if preferred is None:
        # Default to midpoint of the window
        s_h, s_m = map(int, start.split(":"))
        e_h, e_m = map(int, end.split(":"))
        mid_min = ((s_h * 60 + s_m) + (e_h * 60 + e_m)) // 2
        preferred = f"{mid_min // 60:02d}:{mid_min % 60:02d}"
    if not (start <= preferred <= end):
        raise ParseError(
            f"preferred time {preferred} must fall within window {start}-{end}"
        )

    return ParsedRequest(
        target_date=target,
        course=course,
        preferred_time=preferred,
        window_start=start,
        window_end=end,
        source_message_id=msg_id,
    )
```

- [ ] **Step 5: Run, verify all tests pass**

Run: `.venv/bin/pytest tests/test_parser.py -v`
Expected: 10 PASS. If any fail, fix the parser (likely a regex edge case) and rerun.

- [ ] **Step 6: Commit**

```bash
git add src/teebot/parser.py tests/test_parser.py tests/fixtures/emails/
git commit -m "feat(parser): lenient email request parser with structured + freeform inputs"
```

---

### Task 6: SMTP sender via Gmail

**Files:**
- Create: `src/teebot/mailer.py`
- Create: `tests/test_mailer.py`

- [ ] **Step 1: Write failing tests**

`tests/test_mailer.py`:
```python
"""Tests for SMTP sender."""
from unittest.mock import MagicMock, patch

import pytest

from teebot.mailer import Mailer, OutgoingEmail


@pytest.fixture
def mailer():
    return Mailer(
        smtp_host="smtp.gmail.com",
        smtp_port=587,
        username="teebotcarl@gmail.com",
        app_password="appspecificpassword",
    )


def test_send_returns_message_id(mailer):
    with patch("smtplib.SMTP") as smtp_cls:
        smtp = MagicMock()
        smtp_cls.return_value.__enter__.return_value = smtp
        msg_id = mailer.send(OutgoingEmail(
            to="cpfiffner62@gmail.com",
            subject="Test",
            body="Hello",
        ))
        assert msg_id.startswith("<") and msg_id.endswith(">")
        smtp.starttls.assert_called_once()
        smtp.login.assert_called_once_with("teebotcarl@gmail.com", "appspecificpassword")
        smtp.send_message.assert_called_once()


def test_send_sets_in_reply_to(mailer):
    with patch("smtplib.SMTP") as smtp_cls:
        smtp = MagicMock()
        smtp_cls.return_value.__enter__.return_value = smtp
        mailer.send(OutgoingEmail(
            to="cpfiffner62@gmail.com",
            subject="Re: test",
            body="reply",
            in_reply_to="<orig@gmail.com>",
        ))
        sent = smtp.send_message.call_args[0][0]
        assert sent["In-Reply-To"] == "<orig@gmail.com>"
        assert "<orig@gmail.com>" in sent["References"]
```

- [ ] **Step 2: Run, verify failure**

Run: `.venv/bin/pytest tests/test_mailer.py -v`
Expected: ImportError.

- [ ] **Step 3: Implement `mailer.py`**

`src/teebot/mailer.py`:
```python
"""SMTP sender for outbound emails."""
from __future__ import annotations

import smtplib
import uuid
from dataclasses import dataclass
from email.message import EmailMessage


@dataclass(frozen=True)
class OutgoingEmail:
    to: str
    subject: str
    body: str
    in_reply_to: str | None = None
    from_address: str | None = None  # defaults to Mailer's username


class Mailer:
    def __init__(self, smtp_host: str, smtp_port: int, username: str, app_password: str):
        self._host = smtp_host
        self._port = smtp_port
        self._user = username
        self._pw = app_password

    def send(self, email: OutgoingEmail) -> str:
        msg = EmailMessage()
        msg_id = f"<{uuid.uuid4()}@teebot.local>"
        msg["Message-ID"] = msg_id
        msg["From"] = email.from_address or self._user
        msg["To"] = email.to
        msg["Subject"] = email.subject
        if email.in_reply_to:
            msg["In-Reply-To"] = email.in_reply_to
            msg["References"] = email.in_reply_to
        msg.set_content(email.body)

        with smtplib.SMTP(self._host, self._port) as smtp:
            smtp.starttls()
            smtp.login(self._user, self._pw)
            smtp.send_message(msg)
        return msg_id
```

- [ ] **Step 4: Run tests**

Run: `.venv/bin/pytest tests/test_mailer.py -v`
Expected: 2 PASS.

- [ ] **Step 5: Commit**

```bash
git add src/teebot/mailer.py tests/test_mailer.py
git commit -m "feat(mailer): SMTP sender for Gmail with In-Reply-To threading"
```

---

### Task 7: IMAP receiver + request persistence

**Files:**
- Create: `src/teebot/inbox.py`
- Create: `tests/test_inbox.py`

The inbox module fetches unread messages from the bot's Gmail. The classification (request vs reply vs cancel) is the orchestrator's job (Task 15), not this module.

- [ ] **Step 1: Write failing tests**

`tests/test_inbox.py`:
```python
"""Tests for IMAP receiver."""
from unittest.mock import MagicMock, patch

import pytest

from teebot.inbox import Inbox, RawMessage


def test_fetch_unread_returns_messages():
    raw_bytes = b"From: x@y.com\r\nSubject: test\r\n\r\nbody"
    with patch("imaplib.IMAP4_SSL") as imap_cls:
        imap = MagicMock()
        imap_cls.return_value = imap
        imap.login.return_value = ("OK", [b""])
        imap.select.return_value = ("OK", [b"1"])
        imap.search.return_value = ("OK", [b"1 2"])
        imap.fetch.side_effect = [
            ("OK", [(b"1 (RFC822 {N}", raw_bytes), b")"]),
            ("OK", [(b"2 (RFC822 {N}", raw_bytes), b")"]),
        ]
        inbox = Inbox(
            host="imap.gmail.com",
            username="teebotcarl@gmail.com",
            app_password="appsecret",
            sender_allowlist={"x@y.com"},
        )
        messages = inbox.fetch_unread()
        assert len(messages) == 2
        assert all(isinstance(m, RawMessage) for m in messages)
        assert messages[0].uid == "1"
        assert messages[0].raw == raw_bytes


def test_fetch_filters_by_sender_allowlist():
    foreign = b"From: stranger@bad.com\r\nSubject: spam\r\n\r\nbody"
    legit = b"From: x@y.com\r\nSubject: ok\r\n\r\nbody"
    with patch("imaplib.IMAP4_SSL") as imap_cls:
        imap = MagicMock()
        imap_cls.return_value = imap
        imap.login.return_value = ("OK", [b""])
        imap.select.return_value = ("OK", [b"1"])
        imap.search.return_value = ("OK", [b"10 20"])
        imap.fetch.side_effect = [
            ("OK", [(b"10 (RFC822 {N}", foreign), b")"]),
            ("OK", [(b"20 (RFC822 {N}", legit), b")"]),
        ]
        inbox = Inbox(
            host="imap.gmail.com",
            username="teebotcarl@gmail.com",
            app_password="appsecret",
            sender_allowlist={"x@y.com"},
        )
        messages = inbox.fetch_unread()
        assert len(messages) == 1
        assert messages[0].uid == "20"


def test_mark_seen_called():
    raw = b"From: x@y.com\r\nSubject: t\r\n\r\nb"
    with patch("imaplib.IMAP4_SSL") as imap_cls:
        imap = MagicMock()
        imap_cls.return_value = imap
        imap.login.return_value = ("OK", [b""])
        imap.select.return_value = ("OK", [b"1"])
        imap.search.return_value = ("OK", [b"5"])
        imap.fetch.return_value = ("OK", [(b"5 (RFC822 {N}", raw), b")"])
        inbox = Inbox("imap.gmail.com", "u", "p", {"x@y.com"})
        msgs = inbox.fetch_unread()
        inbox.mark_seen(msgs[0].uid)
        imap.store.assert_called_with(b"5", "+FLAGS", "\\Seen")
```

- [ ] **Step 2: Run, verify failure**

Run: `.venv/bin/pytest tests/test_inbox.py -v`
Expected: ImportError.

- [ ] **Step 3: Implement `inbox.py`**

`src/teebot/inbox.py`:
```python
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
```

- [ ] **Step 4: Run tests**

Run: `.venv/bin/pytest tests/test_inbox.py -v`
Expected: 3 PASS.

- [ ] **Step 5: Commit**

```bash
git add src/teebot/inbox.py tests/test_inbox.py
git commit -m "feat(inbox): IMAP receiver with sender allowlist"
```

---

# PHASE 3: ForeTees client (Tasks 8–12)

Produces: a typed Python client that can log in, fetch a tee sheet, render a slot form, and submit a booking. End state: a CLI test command can authenticate and dump a real tee sheet.

---

### Task 8: ForeTees session wrapper (httpx + audit hooks + detection)

**Files:**
- Create: `src/teebot/foretees/__init__.py`
- Create: `src/teebot/foretees/session.py`
- Create: `tests/test_foretees_session.py`

- [ ] **Step 1: Write failing tests**

`tests/test_foretees_session.py`:
```python
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
        lambda req: httpx.Response(200, text="<html>Please complete the captcha verification</html>")
    )
    with pytest.raises(DetectionSignal) as exc:
        s.client.get("https://www1.foretees.com/test")
    assert "captcha" in str(exc.value).lower() or "verification" in str(exc.value).lower()
    s.close()
```

- [ ] **Step 2: Run, verify failure**

Run: `.venv/bin/pytest tests/test_foretees_session.py -v`
Expected: ImportError.

- [ ] **Step 3: Create `src/teebot/foretees/__init__.py`**

```python
"""ForeTees HTTP client subpackage."""
```

- [ ] **Step 4: Implement `session.py`**

`src/teebot/foretees/session.py`:
```python
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
            http2=True,
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
        # Read response body for keyword check (httpx reads lazily but for
        # detection we need text). Only check if content-type is HTML.
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
```

- [ ] **Step 5: Run tests**

Run: `.venv/bin/pytest tests/test_foretees_session.py -v`
Expected: 3 PASS.

- [ ] **Step 6: Commit**

```bash
git add src/teebot/foretees/__init__.py src/teebot/foretees/session.py tests/test_foretees_session.py
git commit -m "feat(foretees): httpx session wrapper with cookies + audit hooks"
```

---

### Task 9: Authentication flow (Clubhouse + ForeTees SSO)

**Files:**
- Create: `src/teebot/foretees/auth.py`
- Create: `tests/test_foretees_auth.py`

- [ ] **Step 1: Write failing tests**

`tests/test_foretees_auth.py`:
```python
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
        return httpx.Response(200, text=_LOGIN_PAGE_HTML)
    if req.url.path == "/login.aspx" and req.method == "POST":
        return httpx.Response(
            302,
            headers={"location": "/Member-Central"},
        )
    if req.url.path == "/Member-Central":
        return httpx.Response(200, text=_MEMBER_CENTRAL_HTML)
    if req.url.path == "/foretees/launch.aspx":
        # SSO redirect to ForeTees
        return httpx.Response(
            302,
            headers={"location": "https://www1.foretees.com/v5/pfcc_golf_m56/Member_announce"},
        )
    if req.url.host == "www1.foretees.com":
        return httpx.Response(200, text="<html>Welcome</html>")
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
            return httpx.Response(200, text=_LOGIN_PAGE_HTML)
        if req.url.path == "/login.aspx" and req.method == "POST":
            # Returning the login page again signals failed auth
            return httpx.Response(200, text=_LOGIN_PAGE_HTML + " Invalid username or password.")
        return httpx.Response(404)
    s = ForeTeesSession()
    s.client._transport = httpx.MockTransport(bad_handler)
    with pytest.raises(AuthError) as exc:
        login(s, username="Pfifftex", password="wrong")
    assert "auth" in str(exc.value).lower() or "login" in str(exc.value).lower()
    s.close()
```

- [ ] **Step 2: Run, verify failure**

Run: `.venv/bin/pytest tests/test_foretees_auth.py -v`
Expected: ImportError.

- [ ] **Step 3: Implement `auth.py`**

`src/teebot/foretees/auth.py`:
```python
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
    # Common patterns: anchor whose href contains 'foretees' or 'launch'
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
    # The redirect chain should land us at Member-Central. If the response body
    # is the login page again, auth failed.
    if "Invalid username or password" in r.text or "login.aspx" in str(r.url).lower():
        raise AuthError("Clubhouse Online login failed (invalid credentials?)")
    if r.status_code != 200:
        raise AuthError(f"After login POST, got status {r.status_code}")

    # 3. Find the ForeTees launch link
    ft_href = _extract_foretees_link(r.text)
    if not ft_href.startswith("http"):
        # Relative URL — resolve against current page
        ft_href = str(r.url.join(ft_href))

    # 4. Follow it (will SSO-redirect to www1.foretees.com)
    r = session.client.get(ft_href)
    if r.status_code != 200:
        raise AuthError(f"ForeTees SSO returned {r.status_code}")
    if "www1.foretees.com" not in str(r.url):
        raise AuthError(f"Expected to land on foretees.com but landed at {r.url}")

    return AuthResult(success=True, foretees_landing_url=str(r.url))
```

- [ ] **Step 4: Run tests**

Run: `.venv/bin/pytest tests/test_foretees_auth.py -v`
Expected: 2 PASS.

- [ ] **Step 5: Commit**

```bash
git add src/teebot/foretees/auth.py tests/test_foretees_auth.py
git commit -m "feat(foretees): Clubhouse → SSO → ForeTees auth chain"
```

---

### Task 10: Tee sheet fetch + HTML parse

**Files:**
- Create: `src/teebot/foretees/tee_sheet.py`
- Create: `tests/test_foretees_tee_sheet.py`
- Extract: `tests/fixtures/tee_sheet_sample.html` (from HAR entry 238's response)

- [ ] **Step 1: Extract the sample tee-sheet HTML from the HAR**

Run:
```bash
python3 -c "
import json
with open('/Users/willduncan/teebot/tests/fixtures/pineforest-capture.har') as f:
    har = json.load(f)
body = har['log']['entries'][238]['response']['content']['text']
with open('/Users/willduncan/teebot/tests/fixtures/tee_sheet_sample.html', 'w') as f:
    f.write(body)
print(f'Wrote {len(body)} chars')
"
```

Verify: `ls -lh /Users/willduncan/teebot/tests/fixtures/tee_sheet_sample.html` shows ~100 KB.

- [ ] **Step 2: Write failing tests**

`tests/test_foretees_tee_sheet.py`:
```python
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
        assert s.ttdata  # every available slot has a ttdata token
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
```

- [ ] **Step 3: Run, verify failure**

Run: `.venv/bin/pytest tests/test_foretees_tee_sheet.py -v`
Expected: ImportError.

- [ ] **Step 4: Inspect the HTML to understand its structure**

Run:
```bash
python3 -c "
from bs4 import BeautifulSoup
html = open('/Users/willduncan/teebot/tests/fixtures/tee_sheet_sample.html').read()
soup = BeautifulSoup(html, 'lxml')
# Find a representative slot row — look for elements with 'ttdata' attribute or in onclick
import re
matches = re.findall(r'ttdata[\"\\']?\s*[:=][\"\\']?([A-Za-z0-9+/=]+)', html[:200000])
print(f'Found {len(matches)} ttdata-like values')
print('First 3:', matches[:3])
"
```

(This is an exploratory step — the implementer uses the output to understand how slots are encoded in the HTML. Expected: dozens of ttdata tokens.)

- [ ] **Step 5: Implement `tee_sheet.py`**

`src/teebot/foretees/tee_sheet.py`:
```python
"""Fetch and parse the Member_sheet tee-sheet listing."""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date

from bs4 import BeautifulSoup

from .session import ForeTeesSession

TEE_SHEET_URL_TEMPLATE = (
    "https://www1.foretees.com/v5/pfcc_golf_m56/Member_sheet"
    "?calDate={cal_date}&course=-ALL-&showAvail=-1&displayOpt=0"
)


@dataclass(frozen=True)
class Slot:
    time: str            # 'HH:MM' 24-hour
    course: str          # e.g., 'Green to Gold'
    ttdata: str          # the per-slot token
    index: int
    day_of_week: str     # e.g., 'Wednesday'
    available: bool


def fetch_tee_sheet_html(session: ForeTeesSession, target: date) -> str:
    """GET the Member_sheet endpoint for the target date."""
    cal_date = target.strftime("%m/%d/%Y")
    url = TEE_SHEET_URL_TEMPLATE.format(cal_date=cal_date)
    r = session.client.get(url)
    r.raise_for_status()
    return r.text


# The tee sheet HTML packs each row's data into a JS click handler.
# The exact selector depends on ForeTees markup — these patterns were
# derived from the captured HAR.
_SLOT_RECORD_RE = re.compile(
    r"""onclick=["'][^"']*?
        ttdata["']?\s*[:=]\s*["']([A-Za-z0-9+/=]+)["'][^"']*?
        date["']?\s*[:=]\s*["']?(\d{8})["']?[^"']*?
        index["']?\s*[:=]\s*["']?(\d+)["']?[^"']*?
        time:0["']?\s*[:=]\s*["']([0-9:]+\s*(?:AM|PM))["'][^"']*?
        course["']?\s*[:=]\s*["']([^"']+)["'][^"']*?
        day["']?\s*[:=]\s*["']([^"']+)["']""",
    re.VERBOSE | re.IGNORECASE,
)


def _to_24h(time_12h: str) -> str:
    t = time_12h.strip().upper().replace(" ", "")
    m = re.match(r"(\d{1,2}):(\d{2})(AM|PM)", t)
    if not m:
        raise ValueError(f"unparseable time: {time_12h!r}")
    h = int(m.group(1))
    mi = int(m.group(2))
    if m.group(3) == "PM" and h != 12:
        h += 12
    elif m.group(3) == "AM" and h == 12:
        h = 0
    return f"{h:02d}:{mi:02d}"


def parse_tee_sheet(html: str) -> list[Slot]:
    """Extract all slot records from the Member_sheet HTML."""
    slots: list[Slot] = []
    soup = BeautifulSoup(html, "lxml")
    # Approach 1: find click handlers on rows (most reliable)
    for el in soup.find_all(attrs={"onclick": True}):
        m = _SLOT_RECORD_RE.search(el["onclick"])
        if not m:
            continue
        try:
            time_24 = _to_24h(m.group(4))
        except ValueError:
            continue
        # Available iff the row has no "blocked"/"closed" class
        classes = " ".join(el.get("class") or [])
        avail = "blocked" not in classes.lower() and "closed" not in classes.lower()
        slots.append(Slot(
            time=time_24,
            course=m.group(5).strip(),
            ttdata=m.group(1),
            index=int(m.group(3)),
            day_of_week=m.group(6).strip(),
            available=avail,
        ))
    return slots
```

- [ ] **Step 6: Run tests**

Run: `.venv/bin/pytest tests/test_foretees_tee_sheet.py -v`
Expected: 3 PASS. If the regex doesn't match the HAR fixture, iterate: dump the actual `onclick` strings from the HTML, then adjust the regex.

If the click-handler regex approach yields zero slots (likely — the HAR may use a different encoding like inline `data-*` attributes or a JS config blob), fall back to: search for inline `<script>` JSON blocks containing slot arrays. Use the exploration step's output to identify the actual structure, then rewrite `parse_tee_sheet` to match.

- [ ] **Step 7: Commit**

```bash
git add src/teebot/foretees/tee_sheet.py tests/test_foretees_tee_sheet.py tests/fixtures/tee_sheet_sample.html
git commit -m "feat(foretees): Member_sheet fetch + slot parse"
```

---

### Task 11: Slot-form fetch (extract `id_list` / `id_hash`)

**Files:**
- Create: `src/teebot/foretees/slot_form.py`
- Create: `tests/test_foretees_slot_form.py`
- Extract: `tests/fixtures/slot_form_sample.html` (from HAR entry 266's response)

- [ ] **Step 1: Extract the sample slot-form HTML**

Run:
```bash
python3 -c "
import json
with open('/Users/willduncan/teebot/tests/fixtures/pineforest-capture.har') as f:
    har = json.load(f)
body = har['log']['entries'][266]['response']['content']['text']
with open('/Users/willduncan/teebot/tests/fixtures/slot_form_sample.html', 'w') as f:
    f.write(body)
print(f'Wrote {len(body)} chars')
"
```

- [ ] **Step 2: Write failing tests**

`tests/test_foretees_slot_form.py`:
```python
"""Tests for slot-form fetch and id_list/id_hash extraction."""
from pathlib import Path

import pytest

from teebot.foretees.slot_form import SlotFormData, parse_slot_form

FIXTURE = Path(__file__).parent / "fixtures" / "slot_form_sample.html"


def test_parse_extracts_id_list_and_hash():
    html = FIXTURE.read_text()
    data = parse_slot_form(html)
    assert isinstance(data, SlotFormData)
    assert data.id_list  # not empty
    assert data.id_hash  # not empty


def test_parse_extracts_callback_map():
    html = FIXTURE.read_text()
    data = parse_slot_form(html)
    # The callback_map should have the slot's core fields
    assert "ttdata" in data.callback_map
    assert "date" in data.callback_map
    assert "course" in data.callback_map
    assert "time:0" in data.callback_map
```

- [ ] **Step 3: Run, verify failure**

Run: `.venv/bin/pytest tests/test_foretees_slot_form.py -v`
Expected: ImportError.

- [ ] **Step 4: Implement `slot_form.py`**

`src/teebot/foretees/slot_form.py`:
```python
"""POST Member_slot (slot-click), parse the returned form for ids."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass

from .session import ForeTeesSession
from .tee_sheet import Slot

MEMBER_SLOT_URL = "https://www1.foretees.com/v5/pfcc_golf_m56/Member_slot"


@dataclass(frozen=True)
class SlotFormData:
    id_list: str
    id_hash: str
    callback_map: dict[str, str]
    raw_html: str


def fetch_slot_form(session: ForeTeesSession, slot: Slot, target_date_str: str) -> SlotFormData:
    """POST Member_slot to render the slot's booking form.

    target_date_str must be 'YYYYMMDD'.
    """
    payload = {
        "lstate": "0",
        "newreq": "yes",
        "displayOpt": "0",
        "showAvail": "-1",
        "ttdata": slot.ttdata,
        "date": target_date_str,
        "index": str(slot.index),
        "course": slot.course,
        "returnCourse": "-ALL-",
        "wasP1": "", "wasP2": "", "wasP3": "", "wasP4": "", "wasP5": "",
        "p5": "Yes",
        "time:0": _to_12h(slot.time),
        "day": slot.day_of_week,
        "contimes": "1",
    }
    r = session.client.post(MEMBER_SLOT_URL, data=payload)
    r.raise_for_status()
    return parse_slot_form(r.text)


def _to_12h(t24: str) -> str:
    h, m = map(int, t24.split(":"))
    ampm = "AM" if h < 12 else "PM"
    h12 = h % 12 or 12
    return f"{h12}:{m:02d} {ampm}"


# The slot-form response embeds a JS config block. We pull out the
# slot_submit_map values and the callback_map. id_list and id_hash are
# specific values inside the rendered form.
_ID_LIST_RE = re.compile(r'name=["\']id_list["\'][^>]*value=["\']([^"\']+)["\']', re.IGNORECASE)
_ID_HASH_RE = re.compile(r'name=["\']id_hash["\'][^>]*value=["\']([^"\']+)["\']', re.IGNORECASE)
_CALLBACK_MAP_RE = re.compile(
    r'callback_map["\']?\s*:\s*(\{[^}]+\})',
    re.DOTALL,
)


def parse_slot_form(html: str) -> SlotFormData:
    """Extract id_list, id_hash, and callback_map from the rendered slot form."""
    id_list_m = _ID_LIST_RE.search(html)
    id_hash_m = _ID_HASH_RE.search(html)
    if not id_list_m or not id_hash_m:
        # Try also extracting from the embedded config JSON
        # Search for "id_list":"..." patterns in the config block
        alt_id_list = re.search(r'"id_list":\s*"([^"]+)"', html)
        alt_id_hash = re.search(r'"id_hash":\s*"([^"]+)"', html)
        id_list = (alt_id_list and alt_id_list.group(1)) or ""
        id_hash = (alt_id_hash and alt_id_hash.group(1)) or ""
    else:
        id_list = id_list_m.group(1)
        id_hash = id_hash_m.group(1)

    callback_map: dict[str, str] = {}
    m = _CALLBACK_MAP_RE.search(html)
    if m:
        try:
            # HTML entities in the JSON
            raw = (
                m.group(1)
                .replace("&quot;", '"')
                .replace("&amp;", "&")
            )
            callback_map = json.loads(raw)
        except json.JSONDecodeError:
            # Fall back to regex-based extraction
            for k, v in re.findall(r'"([^"]+)"\s*:\s*"([^"]+)"', m.group(1).replace("&quot;", '"')):
                callback_map[k] = v

    if not id_list or not id_hash:
        raise RuntimeError(
            "Could not extract id_list or id_hash from slot form response"
        )

    return SlotFormData(
        id_list=id_list,
        id_hash=id_hash,
        callback_map=callback_map,
        raw_html=html,
    )
```

- [ ] **Step 5: Run tests**

Run: `.venv/bin/pytest tests/test_foretees_slot_form.py -v`
Expected: 2 PASS. If the patterns don't match the captured HTML, dump the relevant 1000-char window from the fixture and adjust.

- [ ] **Step 6: Commit**

```bash
git add src/teebot/foretees/slot_form.py tests/test_foretees_slot_form.py tests/fixtures/slot_form_sample.html
git commit -m "feat(foretees): slot-form POST + id_list/id_hash extraction"
```

---

### Task 12: Booking submitter

**Files:**
- Create: `src/teebot/foretees/booker.py`
- Create: `tests/test_foretees_booker.py`

- [ ] **Step 1: Write failing tests**

`tests/test_foretees_booker.py`:
```python
"""Tests for the booking submitter."""
from unittest.mock import MagicMock

import httpx
import pytest

from teebot.foretees.booker import BookingResult, submit_booking
from teebot.foretees.session import ForeTeesSession
from teebot.foretees.slot_form import SlotFormData
from teebot.foretees.tee_sheet import Slot


@pytest.fixture
def slot():
    return Slot(
        time="09:08",
        course="Green to Gold",
        ttdata="TOKEN123",
        index=5,
        day_of_week="Sunday",
        available=True,
    )


@pytest.fixture
def slot_form():
    return SlotFormData(
        id_list="ID_LIST_VAL",
        id_hash="ID_HASH_VAL",
        callback_map={
            "lstate": "0", "newreq": "yes", "displayOpt": "0",
            "showAvail": "-1", "ttdata": "TOKEN123",
            "date": "20260524", "index": "5",
            "course": "Green to Gold", "returnCourse": "-ALL-",
            "p5": "Yes", "time:0": "9:08 AM", "day": "Sunday",
            "contimes": "1", "s_c": "pfcc", "s_a": "0", "s_m": "56",
            "json_mode": "true",
        },
        raw_html="",
    )


def test_submit_booking_success(slot, slot_form):
    submitted_body = {}
    def handler(req: httpx.Request) -> httpx.Response:
        # Capture submitted form-data fields
        body = req.content.decode()
        for kv in body.split("&"):
            if "=" in kv:
                k, v = kv.split("=", 1)
                submitted_body[k] = v
        return httpx.Response(
            200,
            json={"status": "success", "reservation_id": "RES12345"},
        )
    s = ForeTeesSession()
    s.client._transport = httpx.MockTransport(handler)
    result = submit_booking(
        s, slot=slot, form=slot_form,
        member_id="10326", member_name="Carl A Pfiffner", member_user="6605",
    )
    s.close()
    assert result.success
    assert result.reservation_id == "RES12345"
    # Validate that critical fields were submitted
    assert submitted_body.get("ttdata") == "TOKEN123"
    assert "player_a" in submitted_body
    assert "user_a" in submitted_body
    assert submitted_body.get("pcw_a") == "CRT"
    assert submitted_body.get("p9_a") == "18"
    assert submitted_body.get("id_list") == "ID_LIST_VAL"
    assert submitted_body.get("id_hash") == "ID_HASH_VAL"


def test_submit_booking_slot_taken(slot, slot_form):
    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"status": "error", "error": "slot already taken"})
    s = ForeTeesSession()
    s.client._transport = httpx.MockTransport(handler)
    result = submit_booking(
        s, slot=slot, form=slot_form,
        member_id="10326", member_name="Carl A Pfiffner", member_user="6605",
    )
    s.close()
    assert not result.success
    assert "taken" in (result.error_message or "").lower()


def test_submit_booking_unexpected_response(slot, slot_form):
    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="<html>blank</html>")
    s = ForeTeesSession()
    s.client._transport = httpx.MockTransport(handler)
    result = submit_booking(
        s, slot=slot, form=slot_form,
        member_id="10326", member_name="Carl A Pfiffner", member_user="6605",
    )
    s.close()
    assert not result.success
    assert result.unexpected_response is True
```

- [ ] **Step 2: Run, verify failure**

Run: `.venv/bin/pytest tests/test_foretees_booker.py -v`
Expected: ImportError.

- [ ] **Step 3: Implement `booker.py`**

`src/teebot/foretees/booker.py`:
```python
"""Submit the final booking POST to Member_slot."""
from __future__ import annotations

import json
from dataclasses import dataclass

from .session import ForeTeesSession
from .slot_form import SlotFormData, MEMBER_SLOT_URL
from .tee_sheet import Slot


@dataclass(frozen=True)
class BookingResult:
    success: bool
    reservation_id: str | None = None
    error_message: str | None = None
    unexpected_response: bool = False
    raw_response: str = ""


def submit_booking(
    session: ForeTeesSession,
    *,
    slot: Slot,
    form: SlotFormData,
    member_id: str,
    member_name: str,
    member_user: str,
) -> BookingResult:
    """POST Member_slot with the full booking payload (Carl + 3 TBDs).

    Returns a BookingResult; never raises (network errors → success=False).
    """
    # Build payload from callback_map + per-player fields
    payload = dict(form.callback_map)  # copy
    payload["id_list"] = form.id_list
    payload["id_hash"] = form.id_hash
    payload["hide_notes"] = ""
    payload["notes"] = ""

    # Player 1 = Carl
    payload["player_a"] = member_name
    payload["user_a"] = member_user
    payload["member_id_a"] = member_id
    payload["player_type_a"] = "Member"
    payload["pcw_a"] = "CRT"
    payload["p9_a"] = "18"
    payload["custom_disp_a"] = ""
    payload["guest_id_a"] = ""

    # Players 2-4 = TBD
    for letter in ("b", "c", "d"):
        payload[f"player_{letter}"] = "TBD"
        payload[f"user_{letter}"] = ""
        payload[f"member_id_{letter}"] = ""
        payload[f"player_type_{letter}"] = "TBD"
        payload[f"pcw_{letter}"] = ""
        payload[f"p9_{letter}"] = "18"
        payload[f"custom_disp_{letter}"] = ""
        payload[f"guest_id_{letter}"] = ""

    # Ensure json_mode for parseable responses
    payload["json_mode"] = "true"

    try:
        r = session.client.post(MEMBER_SLOT_URL, data=payload)
    except Exception as e:
        return BookingResult(success=False, error_message=f"network: {e}", raw_response="")

    if r.status_code != 200:
        return BookingResult(
            success=False,
            error_message=f"HTTP {r.status_code}",
            raw_response=r.text,
        )

    text = r.text
    # Try parsing as JSON first
    try:
        body = json.loads(text)
        if isinstance(body, dict):
            if body.get("status") == "success" or "reservation_id" in body:
                return BookingResult(
                    success=True,
                    reservation_id=body.get("reservation_id") or body.get("id"),
                    raw_response=text,
                )
            err = body.get("error") or body.get("message") or ""
            return BookingResult(
                success=False,
                error_message=str(err),
                raw_response=text,
            )
    except json.JSONDecodeError:
        pass

    # HTML response: look for confirmation keywords
    lower = text.lower()
    if "reserved" in lower or "confirmation" in lower:
        return BookingResult(
            success=True,
            reservation_id=None,
            raw_response=text,
        )
    if "already taken" in lower or "no longer available" in lower:
        return BookingResult(
            success=False,
            error_message="slot taken",
            raw_response=text,
        )
    # Anything else: mark as unexpected
    return BookingResult(
        success=False,
        error_message="unexpected response shape",
        unexpected_response=True,
        raw_response=text,
    )
```

- [ ] **Step 4: Run tests**

Run: `.venv/bin/pytest tests/test_foretees_booker.py -v`
Expected: 3 PASS.

- [ ] **Step 5: Commit**

```bash
git add src/teebot/foretees/booker.py tests/test_foretees_booker.py
git commit -m "feat(foretees): booking submitter with success/failure/unexpected classification"
```

---

# PHASE 4: Orchestrators (Tasks 13–15)

Produces: the booker orchestrator (the 5-phase 8 AM run) and the poller orchestrator (the 30s IMAP loop). End state: end-to-end test against mocked ForeTees passes.

---

### Task 13: Booker orchestrator — pre-flight, auth, warm hold

**Files:**
- Create: `src/teebot/booker_orchestrator.py`
- Create: `tests/test_booker_orchestrator.py`

- [ ] **Step 1: Write failing tests for pre-flight and auth phases**

`tests/test_booker_orchestrator.py`:
```python
"""Tests for the booker orchestrator (5-phase race)."""
from datetime import date, datetime, timedelta
from unittest.mock import MagicMock, patch

import httpx
import pytest

from teebot.booker_orchestrator import (
    BookerOrchestrator,
    BookerOutcome,
    DetectionSignal,
)
from teebot.db import connect, init_schema


@pytest.fixture
def db(tmp_path):
    c = connect(str(tmp_path / "t.db"))
    init_schema(c)
    yield c
    c.close()


def _insert_pending_request(conn, target_date: date):
    conn.execute("""
        INSERT INTO requests (target_date, course, preferred_time,
            window_start, window_end, status, created_at, updated_at)
        VALUES (?, 'Green', '09:00', '08:00', '10:00', 'pending',
            '2026-05-15 12:00', '2026-05-15 12:00')
    """, (target_date.isoformat(),))


def test_preflight_no_request_exits_cleanly(db):
    orch = BookerOrchestrator(
        db=db,
        today=date(2026, 5, 15),
        target_offset_days=5,
        member_id="10326",
        member_name="Carl A Pfiffner",
        member_user="6605",
        foretees_username="x",
        foretees_password="y",
    )
    outcome = orch.run()
    assert outcome.skipped is True
    assert outcome.skipped_reason == "no_pending_request"


def test_preflight_bot_disabled_exits_cleanly(db):
    _insert_pending_request(db, date(2026, 5, 20))
    db.execute("UPDATE config SET bot_enabled = 0")
    orch = BookerOrchestrator(
        db=db,
        today=date(2026, 5, 15),
        target_offset_days=5,
        member_id="10326",
        member_name="Carl A Pfiffner",
        member_user="6605",
        foretees_username="x",
        foretees_password="y",
    )
    outcome = orch.run()
    assert outcome.skipped is True
    assert outcome.skipped_reason == "bot_disabled"


def test_detection_signal_disables_bot(db):
    _insert_pending_request(db, date(2026, 5, 20))
    # Stub all ForeTees calls so they raise DetectionSignal during auth
    with patch("teebot.booker_orchestrator.login") as mock_login:
        mock_login.side_effect = DetectionSignal("datadome cookie set")
        orch = BookerOrchestrator(
            db=db,
            today=date(2026, 5, 15),
            target_offset_days=5,
            member_id="10326",
            member_name="Carl",
            member_user="6605",
            foretees_username="x",
            foretees_password="y",
        )
        outcome = orch.run()
        assert outcome.detection_signal is True
    # Verify bot was disabled
    row = db.execute("SELECT bot_enabled FROM config WHERE id=1").fetchone()
    assert row["bot_enabled"] == 0
```

- [ ] **Step 2: Run, verify failure**

Run: `.venv/bin/pytest tests/test_booker_orchestrator.py -v`
Expected: ImportError.

- [ ] **Step 3: Implement orchestrator skeleton + pre-flight + auth phases**

`src/teebot/booker_orchestrator.py`:
```python
"""The 5-phase booker orchestrator that runs daily at 7:58 AM Central."""
from __future__ import annotations

import sqlite3
import time
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

from .audit import log_event
from .foretees.auth import AuthError, login
from .foretees.session import DetectionSignal, ForeTeesSession


@dataclass
class BookerOutcome:
    skipped: bool = False
    skipped_reason: str = ""
    booked_time: str | None = None
    booked_course: str | None = None
    attempt_count: int = 0
    detection_signal: bool = False
    error_message: str | None = None


class BookerOrchestrator:
    def __init__(
        self,
        *,
        db: sqlite3.Connection,
        today: date,
        target_offset_days: int,
        member_id: str,
        member_name: str,
        member_user: str,
        foretees_username: str,
        foretees_password: str,
    ):
        self.db = db
        self.today = today
        self.target_offset_days = target_offset_days
        self.member_id = member_id
        self.member_name = member_name
        self.member_user = member_user
        self.foretees_username = foretees_username
        self.foretees_password = foretees_password

    def _target_date(self) -> date:
        return self.today + timedelta(days=self.target_offset_days)

    def _audit(self, event: str, **kw) -> None:
        details = {k: v for k, v in kw.items() if k not in ("success", "request_id", "booking_id")}
        log_event(
            self.db,
            event,
            success=kw.get("success", True),
            request_id=kw.get("request_id"),
            booking_id=kw.get("booking_id"),
            details=details or None,
        )

    def _hard_stop(self, reason: str) -> None:
        """Disable the bot in the config table; called on any detection signal."""
        self.db.execute("UPDATE config SET bot_enabled = 0")
        self._audit("hard_stop", success=False, reason=reason)

    def run(self) -> BookerOutcome:
        outcome = BookerOutcome()

        # === Phase 1: Pre-flight ===
        cfg = self.db.execute("SELECT bot_enabled FROM config WHERE id=1").fetchone()
        if cfg is None or cfg["bot_enabled"] == 0:
            outcome.skipped = True
            outcome.skipped_reason = "bot_disabled"
            self._audit("preflight_skipped", success=True, reason="bot_disabled")
            return outcome

        target = self._target_date()
        req = self.db.execute(
            "SELECT * FROM requests WHERE target_date = ? AND status = 'pending'",
            (target.isoformat(),),
        ).fetchone()
        if req is None:
            outcome.skipped = True
            outcome.skipped_reason = "no_pending_request"
            self._audit("preflight_skipped", success=True, reason="no_pending_request", target_date=target.isoformat())
            return outcome

        self._audit("preflight_ok", success=True, request_id=req["id"], target_date=target.isoformat())

        # === Phase 2: Auth ===
        try:
            with ForeTeesSession(audit_hook=lambda evt, **kw: self._audit(evt, success=True, **kw)) as sess:
                try:
                    auth_result = login(
                        sess,
                        username=self.foretees_username,
                        password=self.foretees_password,
                    )
                except DetectionSignal as ds:
                    outcome.detection_signal = True
                    outcome.error_message = str(ds)
                    self._hard_stop(f"auth: {ds}")
                    return outcome
                except AuthError as e:
                    outcome.error_message = f"auth_failed: {e}"
                    self._audit("auth_failed", success=False, error=str(e))
                    self.db.execute(
                        "UPDATE requests SET status='failed', updated_at=? WHERE id=?",
                        (datetime.utcnow().isoformat(), req["id"]),
                    )
                    return outcome
                self._audit("auth_ok", success=True, landing=auth_result.foretees_landing_url, request_id=req["id"])

                # === Phases 3, 4, 5 implemented in Task 14 ===
                # For now, just mark the request 'attempted'
                self.db.execute(
                    "UPDATE requests SET status='attempted', updated_at=? WHERE id=?",
                    (datetime.utcnow().isoformat(), req["id"]),
                )
        except Exception as e:
            outcome.error_message = f"orchestrator_error: {e}"
            self._audit("orchestrator_error", success=False, error=str(e))

        return outcome
```

- [ ] **Step 4: Run tests, verify 3 pass**

Run: `.venv/bin/pytest tests/test_booker_orchestrator.py -v`
Expected: 3 PASS.

- [ ] **Step 5: Commit**

```bash
git add src/teebot/booker_orchestrator.py tests/test_booker_orchestrator.py
git commit -m "feat(booker): orchestrator skeleton with preflight + auth phase"
```

---

### Task 14: Booker orchestrator — race phase + slot-selection loop + result emails

**Files:**
- Modify: `src/teebot/booker_orchestrator.py` (extend the `run()` method)
- Modify: `tests/test_booker_orchestrator.py` (add race-phase tests)

- [ ] **Step 1: Add new tests for race phase**

Append to `tests/test_booker_orchestrator.py`:

```python
from teebot.foretees.tee_sheet import Slot
from teebot.foretees.slot_form import SlotFormData
from teebot.foretees.booker import BookingResult


def test_race_books_preferred_when_available(db):
    _insert_pending_request(db, date(2026, 5, 20))
    fake_slots = [
        Slot("08:00", "Green", "TKN_08", 1, "Wednesday", True),
        Slot("09:00", "Green", "TKN_09", 5, "Wednesday", True),
        Slot("09:08", "Green", "TKN_0908", 6, "Wednesday", True),
        Slot("10:00", "Green", "TKN_10", 11, "Wednesday", True),
    ]
    fake_form = SlotFormData("ID_L", "ID_H", {"date":"20260520","ttdata":"TKN_09","course":"Green","index":"5","time:0":"9:00 AM","day":"Wednesday"}, "")
    with patch("teebot.booker_orchestrator.login") as mock_login, \
         patch("teebot.booker_orchestrator.fetch_tee_sheet_html") as mock_fetch, \
         patch("teebot.booker_orchestrator.parse_tee_sheet") as mock_parse, \
         patch("teebot.booker_orchestrator.fetch_slot_form") as mock_slotform, \
         patch("teebot.booker_orchestrator.submit_booking") as mock_submit, \
         patch("teebot.booker_orchestrator._wait_until_T0") as mock_wait, \
         patch("teebot.booker_orchestrator._warm_hold") as mock_warm:
        mock_login.return_value = MagicMock(foretees_landing_url="http://www1.foretees.com/landed")
        mock_fetch.return_value = "<html/>"
        mock_parse.return_value = fake_slots
        mock_slotform.return_value = fake_form
        mock_submit.return_value = BookingResult(success=True, reservation_id="R123")
        mock_wait.return_value = None
        mock_warm.return_value = None
        orch = BookerOrchestrator(
            db=db, today=date(2026, 5, 15), target_offset_days=5,
            member_id="10326", member_name="Carl", member_user="6605",
            foretees_username="x", foretees_password="y",
        )
        outcome = orch.run()
        assert outcome.booked_time == "09:00"
        assert outcome.attempt_count == 1
    row = db.execute("SELECT status FROM requests WHERE target_date='2026-05-20'").fetchone()
    assert row["status"] == "succeeded"


def test_race_walks_outward_when_preferred_taken(db):
    _insert_pending_request(db, date(2026, 5, 20))
    fake_slots = [
        Slot("08:00", "Green", "TKN_08", 1, "Wednesday", True),
        Slot("09:00", "Green", "TKN_09", 5, "Wednesday", True),  # preferred
        Slot("09:08", "Green", "TKN_0908", 6, "Wednesday", True),
        Slot("10:00", "Green", "TKN_10", 11, "Wednesday", True),
    ]
    fake_form = SlotFormData("ID_L", "ID_H", {}, "")
    with patch("teebot.booker_orchestrator.login") as mock_login, \
         patch("teebot.booker_orchestrator.fetch_tee_sheet_html") as mock_fetch, \
         patch("teebot.booker_orchestrator.parse_tee_sheet") as mock_parse, \
         patch("teebot.booker_orchestrator.fetch_slot_form") as mock_slotform, \
         patch("teebot.booker_orchestrator.submit_booking") as mock_submit, \
         patch("teebot.booker_orchestrator._wait_until_T0") as mock_wait, \
         patch("teebot.booker_orchestrator._warm_hold") as mock_warm:
        mock_login.return_value = MagicMock(foretees_landing_url="x")
        mock_fetch.return_value = "<html/>"
        mock_parse.return_value = fake_slots
        mock_slotform.return_value = fake_form
        # First attempt fails ("slot taken"); second succeeds
        mock_submit.side_effect = [
            BookingResult(success=False, error_message="slot taken"),
            BookingResult(success=True, reservation_id="R987"),
        ]
        mock_wait.return_value = None
        mock_warm.return_value = None
        orch = BookerOrchestrator(
            db=db, today=date(2026, 5, 15), target_offset_days=5,
            member_id="10326", member_name="Carl", member_user="6605",
            foretees_username="x", foretees_password="y",
        )
        outcome = orch.run()
        assert outcome.attempt_count == 2
        # The successful booking should be 09:08 (closest to 09:00 after the 09:00 slot itself)
        assert outcome.booked_time == "09:08"


def test_race_all_slots_taken_marks_failed(db):
    _insert_pending_request(db, date(2026, 5, 20))
    fake_slots = [
        Slot("09:00", "Green", "T", 5, "Wednesday", True),
    ]
    fake_form = SlotFormData("ID_L", "ID_H", {}, "")
    with patch("teebot.booker_orchestrator.login") as mock_login, \
         patch("teebot.booker_orchestrator.fetch_tee_sheet_html"), \
         patch("teebot.booker_orchestrator.parse_tee_sheet", return_value=fake_slots), \
         patch("teebot.booker_orchestrator.fetch_slot_form", return_value=fake_form), \
         patch("teebot.booker_orchestrator.submit_booking", return_value=BookingResult(success=False, error_message="slot taken")), \
         patch("teebot.booker_orchestrator._wait_until_T0"), \
         patch("teebot.booker_orchestrator._warm_hold"):
        mock_login.return_value = MagicMock(foretees_landing_url="x")
        orch = BookerOrchestrator(
            db=db, today=date(2026, 5, 15), target_offset_days=5,
            member_id="10326", member_name="Carl", member_user="6605",
            foretees_username="x", foretees_password="y",
        )
        outcome = orch.run()
        assert outcome.booked_time is None
    row = db.execute("SELECT status FROM requests WHERE target_date='2026-05-20'").fetchone()
    assert row["status"] == "failed"
```

- [ ] **Step 2: Run new tests, verify failure**

Run: `.venv/bin/pytest tests/test_booker_orchestrator.py -v`
Expected: New tests FAIL (existing 3 still PASS).

- [ ] **Step 3: Extend `booker_orchestrator.py` to implement race phase**

Replace the entire `src/teebot/booker_orchestrator.py` with:

```python
"""The 5-phase booker orchestrator that runs daily at 7:58 AM Central."""
from __future__ import annotations

import sqlite3
import time
from dataclasses import dataclass
from datetime import date, datetime, time as dtime, timedelta
from zoneinfo import ZoneInfo

from .audit import log_event
from .foretees.auth import AuthError, login
from .foretees.session import DetectionSignal, ForeTeesSession
from .foretees.tee_sheet import Slot, fetch_tee_sheet_html, parse_tee_sheet
from .foretees.slot_form import SlotFormData, fetch_slot_form
from .foretees.booker import BookingResult, submit_booking


@dataclass
class BookerOutcome:
    skipped: bool = False
    skipped_reason: str = ""
    booked_time: str | None = None
    booked_course: str | None = None
    booked_reservation_id: str | None = None
    attempt_count: int = 0
    detection_signal: bool = False
    error_message: str | None = None
    booking_id: int | None = None


def _time_to_minutes(t: str) -> int:
    h, m = map(int, t.split(":"))
    return h * 60 + m


def _wait_until_T0(target_dt: datetime) -> None:
    """Sleep until target_dt with sub-second precision."""
    while True:
        now = datetime.now(target_dt.tzinfo)
        remaining = (target_dt - now).total_seconds()
        if remaining <= 0:
            return
        if remaining > 1.0:
            time.sleep(remaining - 0.5)
        else:
            # Busy-wait the final ~500ms for precision
            time.sleep(0.001)


def _warm_hold(session: ForeTeesSession, until_dt: datetime, ping_url: str) -> None:
    """Keep session warm by pinging a benign endpoint every 20s."""
    while True:
        now = datetime.now(until_dt.tzinfo)
        if now >= until_dt:
            return
        try:
            session.client.get(ping_url)
        except Exception:
            pass
        # Sleep until the next 20s interval or the deadline
        sleep_for = min(20.0, (until_dt - now).total_seconds() - 5.0)
        if sleep_for <= 0:
            return
        time.sleep(sleep_for)


def _prioritize_slots(
    slots: list[Slot],
    course: str,
    preferred: str,
    window_start: str,
    window_end: str,
) -> list[Slot]:
    """Return slots that match course + fall within window, sorted by closeness to preferred."""
    pref_min = _time_to_minutes(preferred)
    ws_min = _time_to_minutes(window_start)
    we_min = _time_to_minutes(window_end)

    matched: list[tuple[int, Slot]] = []
    for s in slots:
        if not s.available:
            continue
        # Course match: 'Green' should match 'Green to Gold' / 'Green' / 'Green/Gold' etc.
        if course.lower() not in s.course.lower():
            continue
        m = _time_to_minutes(s.time)
        if not (ws_min <= m <= we_min):
            continue
        matched.append((abs(m - pref_min), s))
    matched.sort(key=lambda x: x[0])
    return [s for _, s in matched]


class BookerOrchestrator:
    BENIGN_PING_URL = "https://www1.foretees.com/v5/pfcc_golf_m56/Member_announce"

    def __init__(
        self,
        *,
        db: sqlite3.Connection,
        today: date,
        target_offset_days: int,
        member_id: str,
        member_name: str,
        member_user: str,
        foretees_username: str,
        foretees_password: str,
        tz: str = "America/Chicago",
        race_at_local_time: dtime = dtime(8, 0, 0),
    ):
        self.db = db
        self.today = today
        self.target_offset_days = target_offset_days
        self.member_id = member_id
        self.member_name = member_name
        self.member_user = member_user
        self.foretees_username = foretees_username
        self.foretees_password = foretees_password
        self.tz = ZoneInfo(tz)
        self.race_at_local_time = race_at_local_time

    def _target_date(self) -> date:
        return self.today + timedelta(days=self.target_offset_days)

    def _audit(self, event: str, **kw) -> None:
        details = {k: v for k, v in kw.items() if k not in ("success", "request_id", "booking_id")}
        log_event(
            self.db,
            event,
            success=kw.get("success", True),
            request_id=kw.get("request_id"),
            booking_id=kw.get("booking_id"),
            details=details or None,
        )

    def _hard_stop(self, reason: str) -> None:
        self.db.execute("UPDATE config SET bot_enabled = 0")
        self._audit("hard_stop", success=False, reason=reason)

    def run(self) -> BookerOutcome:
        outcome = BookerOutcome()

        # === Phase 1: Pre-flight ===
        cfg = self.db.execute("SELECT bot_enabled FROM config WHERE id=1").fetchone()
        if cfg is None or cfg["bot_enabled"] == 0:
            outcome.skipped = True
            outcome.skipped_reason = "bot_disabled"
            self._audit("preflight_skipped", success=True, reason="bot_disabled")
            return outcome

        target = self._target_date()
        req = self.db.execute(
            "SELECT * FROM requests WHERE target_date = ? AND status = 'pending'",
            (target.isoformat(),),
        ).fetchone()
        if req is None:
            outcome.skipped = True
            outcome.skipped_reason = "no_pending_request"
            self._audit("preflight_skipped", success=True, reason="no_pending_request",
                        target_date=target.isoformat())
            return outcome
        request_id = req["id"]
        self._audit("preflight_ok", success=True, request_id=request_id,
                    target_date=target.isoformat())

        # === Phase 2: Auth ===
        with ForeTeesSession(audit_hook=lambda evt, **kw: self._audit(evt, success=True, **kw)) as sess:
            try:
                try:
                    auth_result = login(sess, username=self.foretees_username, password=self.foretees_password)
                except AuthError as e:
                    outcome.error_message = f"auth_failed: {e}"
                    self._audit("auth_failed", success=False, error=str(e), request_id=request_id)
                    self.db.execute(
                        "UPDATE requests SET status='failed', updated_at=? WHERE id=?",
                        (datetime.utcnow().isoformat(), request_id),
                    )
                    return outcome
                self._audit("auth_ok", success=True, landing=auth_result.foretees_landing_url,
                            request_id=request_id)

                # === Phase 3: Warm hold ===
                race_dt = datetime.combine(self.today, self.race_at_local_time, tzinfo=self.tz)
                warm_until = race_dt - timedelta(seconds=5)
                _warm_hold(sess, warm_until, self.BENIGN_PING_URL)
                self._audit("warm_hold_complete", success=True, request_id=request_id)

                # === Phase 4: Race ===
                _wait_until_T0(race_dt)
                t0_monotonic = time.monotonic()
                tee_sheet_html = fetch_tee_sheet_html(sess, target)
                slots = parse_tee_sheet(tee_sheet_html)
                self._audit("tee_sheet_fetched", success=True, slot_count=len(slots), request_id=request_id)

                prioritized = _prioritize_slots(
                    slots,
                    course=req["course"],
                    preferred=req["preferred_time"],
                    window_start=req["window_start"],
                    window_end=req["window_end"],
                )
                self._audit("slots_prioritized", success=True,
                            candidate_count=len(prioritized), request_id=request_id)

                target_date_str = target.strftime("%Y%m%d")
                attempts = 0
                successful_slot: Slot | None = None
                successful_result: BookingResult | None = None
                for slot in prioritized:
                    attempts += 1
                    self._audit("slot_attempt", success=True, slot_time=slot.time,
                                attempt=attempts, request_id=request_id)
                    try:
                        form = fetch_slot_form(sess, slot, target_date_str)
                    except DetectionSignal:
                        raise  # propagate to outer handler
                    except Exception as e:
                        self._audit("slot_form_failed", success=False, error=str(e),
                                    slot_time=slot.time, request_id=request_id)
                        continue
                    result = submit_booking(
                        sess,
                        slot=slot,
                        form=form,
                        member_id=self.member_id,
                        member_name=self.member_name,
                        member_user=self.member_user,
                    )
                    self._audit("booking_attempted", success=result.success,
                                slot_time=slot.time, result_msg=result.error_message,
                                request_id=request_id)
                    if result.success:
                        successful_slot = slot
                        successful_result = result
                        break
                    if result.unexpected_response:
                        self._audit("stop_due_to_unexpected", success=False,
                                    request_id=request_id)
                        break
                latency_ms = int((time.monotonic() - t0_monotonic) * 1000)
            except DetectionSignal as ds:
                outcome.detection_signal = True
                outcome.error_message = str(ds)
                self._hard_stop(f"detection: {ds}")
                return outcome

            # === Phase 5: Confirm ===
            outcome.attempt_count = attempts
            if successful_slot is not None and successful_result is not None:
                cur = self.db.execute(
                    """INSERT INTO bookings
                         (request_id, target_date, booked_time, course,
                          foretees_reservation_id, attempt_count, booking_latency_ms, created_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        request_id, target.isoformat(),
                        successful_slot.time, successful_slot.course,
                        successful_result.reservation_id, attempts,
                        latency_ms, datetime.utcnow().isoformat(),
                    ),
                )
                outcome.booking_id = cur.lastrowid
                outcome.booked_time = successful_slot.time
                outcome.booked_course = successful_slot.course
                outcome.booked_reservation_id = successful_result.reservation_id
                self.db.execute(
                    "UPDATE requests SET status='succeeded', updated_at=? WHERE id=?",
                    (datetime.utcnow().isoformat(), request_id),
                )
                self._audit("booking_succeeded", success=True, request_id=request_id,
                            booking_id=outcome.booking_id, latency_ms=latency_ms)
            else:
                self.db.execute(
                    """INSERT INTO bookings
                         (request_id, target_date, attempt_count, booking_latency_ms,
                          failure_reason, created_at)
                       VALUES (?, ?, ?, ?, ?, ?)""",
                    (
                        request_id, target.isoformat(),
                        attempts, latency_ms,
                        outcome.error_message or "no_slots_in_window",
                        datetime.utcnow().isoformat(),
                    ),
                )
                self.db.execute(
                    "UPDATE requests SET status='failed', updated_at=? WHERE id=?",
                    (datetime.utcnow().isoformat(), request_id),
                )
                self._audit("booking_failed", success=False, request_id=request_id,
                            attempts=attempts)

        return outcome
```

- [ ] **Step 4: Run all tests, verify all pass**

Run: `.venv/bin/pytest tests/test_booker_orchestrator.py -v`
Expected: 6 PASS.

- [ ] **Step 5: Commit**

```bash
git add src/teebot/booker_orchestrator.py tests/test_booker_orchestrator.py
git commit -m "feat(booker): race phase + slot prioritization + result persistence"
```

---

### Task 15: Poller orchestrator (IMAP loop)

**Files:**
- Create: `src/teebot/poller_orchestrator.py`
- Create: `tests/test_poller_orchestrator.py`

The poller (1) classifies incoming messages as new requests, cancels, or partner-followup replies; (2) writes to DB; (3) sends confirmation replies. It does NOT handle the partner-update against ForeTees in v1 — that's deferred (Carl edits manually for now). v1 just acks what Carl chose.

- [ ] **Step 1: Write failing tests**

`tests/test_poller_orchestrator.py`:
```python
"""Tests for the poller orchestrator."""
from datetime import date, datetime
from unittest.mock import MagicMock

import pytest

from teebot.db import connect, init_schema
from teebot.inbox import RawMessage
from teebot.poller_orchestrator import PollerOrchestrator


@pytest.fixture
def db(tmp_path):
    c = connect(str(tmp_path / "t.db"))
    init_schema(c)
    yield c
    c.close()


def _email_bytes(*, frm: str, body: str, subject: str = "tee time", in_reply_to: str | None = None) -> bytes:
    headers = f"From: {frm}\r\nTo: bot@teebot.local\r\nSubject: {subject}\r\n"
    if in_reply_to:
        headers += f"In-Reply-To: {in_reply_to}\r\n"
    headers += "\r\n"
    return (headers + body).encode()


def test_processes_new_request(db):
    inbox = MagicMock()
    mailer = MagicMock()
    mailer.send.return_value = "<sent-1@teebot.local>"
    inbox.fetch_unread.return_value = [
        RawMessage(
            uid="1",
            raw=_email_bytes(
                frm="cpfiffner62@gmail.com",
                body="Day: Sunday May 24\nCourse: Green\nWindow: 8 to 10 AM\nPreferred: 9:00 AM\n",
            ),
            sender="cpfiffner62@gmail.com",
        )
    ]
    orch = PollerOrchestrator(
        db=db, inbox=inbox, mailer=mailer,
        bot_email="teebotcarl@gmail.com", carl_email="cpfiffner62@gmail.com",
        today=date(2026, 5, 15),
    )
    orch.run_once()
    rows = list(db.execute("SELECT * FROM requests WHERE status='pending'"))
    assert len(rows) == 1
    assert rows[0]["target_date"] == "2026-05-24"
    inbox.mark_seen.assert_called_with("1")
    mailer.send.assert_called_once()
    sent = mailer.send.call_args[0][0]
    assert "Got it" in sent.body
    assert "Sunday" in sent.body


def test_processes_cancel(db):
    # Pre-insert a pending request
    db.execute("""
        INSERT INTO requests (target_date, course, preferred_time,
            window_start, window_end, status, created_at, updated_at)
        VALUES ('2026-05-24', 'Green', '09:00', '08:00', '10:00',
            'pending', '2026-05-15 12:00', '2026-05-15 12:00')
    """)
    inbox = MagicMock()
    mailer = MagicMock()
    mailer.send.return_value = "<sent-2@teebot.local>"
    inbox.fetch_unread.return_value = [
        RawMessage(
            uid="2",
            raw=_email_bytes(frm="cpfiffner62@gmail.com", subject="Re: tee time", body="cancel"),
            sender="cpfiffner62@gmail.com",
        )
    ]
    orch = PollerOrchestrator(
        db=db, inbox=inbox, mailer=mailer,
        bot_email="teebotcarl@gmail.com", carl_email="cpfiffner62@gmail.com",
        today=date(2026, 5, 15),
    )
    orch.run_once()
    rows = list(db.execute("SELECT status FROM requests"))
    # The pending row should have been cancelled (or deleted)
    assert all(r["status"] == "cancelled" for r in rows)


def test_replies_with_format_help_on_malformed(db):
    inbox = MagicMock()
    mailer = MagicMock()
    mailer.send.return_value = "<sent-3@teebot.local>"
    inbox.fetch_unread.return_value = [
        RawMessage(
            uid="3",
            raw=_email_bytes(frm="cpfiffner62@gmail.com", body="hi can I tee?"),
            sender="cpfiffner62@gmail.com",
        )
    ]
    orch = PollerOrchestrator(
        db=db, inbox=inbox, mailer=mailer,
        bot_email="teebotcarl@gmail.com", carl_email="cpfiffner62@gmail.com",
        today=date(2026, 5, 15),
    )
    orch.run_once()
    sent = mailer.send.call_args[0][0]
    assert "couldn't understand" in sent.body.lower() or "format" in sent.body.lower()


def test_handles_partner_reply(db):
    # Pre-insert a booking with a known confirmation_message_id
    db.execute("""
        INSERT INTO requests (id, target_date, course, preferred_time,
            window_start, window_end, status, created_at, updated_at)
        VALUES (1, '2026-05-24', 'Green', '09:00', '08:00', '10:00',
            'succeeded', '2026-05-15 12:00', '2026-05-15 12:00')
    """)
    db.execute("""
        INSERT INTO bookings (id, request_id, target_date, booked_time, course,
            partner_status, confirmation_message_id, created_at)
        VALUES (1, 1, '2026-05-24', '09:00', 'Green', 'pending_choice',
            '<conf-1@teebot.local>', '2026-05-15 12:01')
    """)
    inbox = MagicMock()
    mailer = MagicMock()
    mailer.send.return_value = "<sent-4@teebot.local>"
    inbox.fetch_unread.return_value = [
        RawMessage(
            uid="4",
            raw=_email_bytes(
                frm="cpfiffner62@gmail.com",
                subject="Re: ✓ Booked",
                body="names: Bob Smith, Tom Jones, Jim Davis",
                in_reply_to="<conf-1@teebot.local>",
            ),
            sender="cpfiffner62@gmail.com",
        )
    ]
    orch = PollerOrchestrator(
        db=db, inbox=inbox, mailer=mailer,
        bot_email="teebotcarl@gmail.com", carl_email="cpfiffner62@gmail.com",
        today=date(2026, 5, 15),
    )
    orch.run_once()
    row = db.execute("SELECT partner_status, partner_names FROM bookings WHERE id=1").fetchone()
    assert row["partner_status"] == "names_provided"
    import json
    assert json.loads(row["partner_names"]) == ["Bob Smith", "Tom Jones", "Jim Davis"]
```

- [ ] **Step 2: Run, verify failure**

Run: `.venv/bin/pytest tests/test_poller_orchestrator.py -v`
Expected: ImportError.

- [ ] **Step 3: Implement `poller_orchestrator.py`**

`src/teebot/poller_orchestrator.py`:
```python
"""IMAP poller: classifies inbound messages and updates DB + sends replies."""
from __future__ import annotations

import email
import email.policy
import json
import re
import sqlite3
from dataclasses import dataclass
from datetime import date, datetime

from .audit import log_event
from .inbox import Inbox, RawMessage
from .mailer import Mailer, OutgoingEmail
from .parser import ParseError, parse_cancel, parse_request_email


_FORMAT_HELP = """\
I couldn't understand your message. Please send it in this format:

  Day: Sunday May 24
  Course: Green
  Window: 8:00 AM to 10:00 AM
  Preferred: 9:00 AM

Or free-text like: "Sunday, Green, 8-10 AM, prefer 9".
"""


_NAMES_RE = re.compile(r"names\s*[:\s]\s*(.+)", re.IGNORECASE)


class PollerOrchestrator:
    def __init__(
        self,
        *,
        db: sqlite3.Connection,
        inbox: Inbox,
        mailer: Mailer,
        bot_email: str,
        carl_email: str,
        today: date,
    ):
        self.db = db
        self.inbox = inbox
        self.mailer = mailer
        self.bot_email = bot_email
        self.carl_email = carl_email
        self.today = today

    def _audit(self, event: str, **kw) -> None:
        log_event(
            self.db, event,
            success=kw.pop("success", True),
            request_id=kw.pop("request_id", None),
            booking_id=kw.pop("booking_id", None),
            details=kw or None,
        )

    def _get_in_reply_to(self, raw: bytes) -> str | None:
        msg = email.message_from_bytes(raw, policy=email.policy.default)
        return msg.get("In-Reply-To")

    def _find_booking_by_confirmation_id(self, msg_id: str) -> sqlite3.Row | None:
        return self.db.execute(
            "SELECT * FROM bookings WHERE confirmation_message_id = ?",
            (msg_id,),
        ).fetchone()

    def _handle_partner_reply(self, raw: bytes, booking: sqlite3.Row, *, in_reply_to: str) -> None:
        body = email.message_from_bytes(raw, policy=email.policy.default).get_content().lower()
        if "names" in body:
            m = _NAMES_RE.search(body)
            if m:
                names_str = m.group(1).strip()
                names = [n.strip() for n in re.split(r"[,;]| and ", names_str) if n.strip()]
                self.db.execute(
                    "UPDATE bookings SET partner_status='names_provided', partner_names=? WHERE id=?",
                    (json.dumps(names), booking["id"]),
                )
                ack = f"Got it. Names recorded: {', '.join(names)}.\n\nYou can edit anytime in ForeTees."
                self._audit("partner_names_set", booking_id=booking["id"], names=names)
        elif "leave open" in body or re.search(r"\bopen\b", body):
            self.db.execute(
                "UPDATE bookings SET partner_status='leave_open' WHERE id=?",
                (booking["id"],),
            )
            ack = "OK, the other 3 spots will stay open. You can edit anytime in ForeTees."
            self._audit("partner_leave_open", booking_id=booking["id"])
        elif "tbd" in body:
            self.db.execute(
                "UPDATE bookings SET partner_status='all_tbd' WHERE id=?",
                (booking["id"],),
            )
            ack = "OK, the other 3 spots are TBD. You can edit anytime in ForeTees."
            self._audit("partner_all_tbd", booking_id=booking["id"])
        else:
            ack = (
                "I didn't recognize your choice. Reply with one of:\n"
                "  - 'leave open'\n"
                "  - 'TBD'\n"
                "  - 'names: Bob, Tom, Jim'"
            )
            self._audit("partner_unparseable", success=False, booking_id=booking["id"])
        self.mailer.send(OutgoingEmail(
            to=self.carl_email,
            subject="Re: tee time partner choice",
            body=ack,
            in_reply_to=in_reply_to,
            from_address=self.bot_email,
        ))

    def _handle_cancel(self, msg: RawMessage) -> None:
        self.db.execute(
            "UPDATE requests SET status='cancelled', updated_at=? WHERE status='pending'",
            (datetime.utcnow().isoformat(),),
        )
        self.mailer.send(OutgoingEmail(
            to=self.carl_email,
            subject="Cancelled",
            body="Your pending request has been cancelled.",
            from_address=self.bot_email,
        ))
        self._audit("request_cancelled", uid=msg.uid)

    def _handle_request(self, msg: RawMessage) -> None:
        try:
            parsed = parse_request_email(msg.raw, today=self.today)
        except ParseError as e:
            self._audit("parse_failed", success=False, uid=msg.uid, error=str(e))
            self.mailer.send(OutgoingEmail(
                to=self.carl_email,
                subject="Re: tee time",
                body=_FORMAT_HELP + f"\n(Details: {e})",
                from_address=self.bot_email,
            ))
            return

        # Upsert: cancel any existing pending row for this target_date, then insert
        self.db.execute(
            "UPDATE requests SET status='cancelled', updated_at=? "
            "WHERE target_date=? AND status='pending'",
            (datetime.utcnow().isoformat(), parsed.target_date.isoformat()),
        )
        cur = self.db.execute(
            """INSERT INTO requests
                 (target_date, course, preferred_time, window_start, window_end,
                  status, source_message_id, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, 'pending', ?, ?, ?)""",
            (
                parsed.target_date.isoformat(),
                parsed.course,
                parsed.preferred_time,
                parsed.window_start,
                parsed.window_end,
                parsed.source_message_id,
                datetime.utcnow().isoformat(),
                datetime.utcnow().isoformat(),
            ),
        )
        rid = cur.lastrowid
        self._audit("request_received", request_id=rid, target_date=parsed.target_date.isoformat())
        confirm_body = (
            f"Got it, Carl.\n\n"
            f"  Day:       {parsed.target_date.strftime('%A, %B %d')}\n"
            f"  Course:    {parsed.course}\n"
            f"  Window:    {parsed.window_start} to {parsed.window_end}\n"
            f"  Preferred: {parsed.preferred_time}\n\n"
            "I'll try to book this at 8:00 AM Central on the booking morning.\n\n"
            "To cancel, reply with \"cancel\". To change, just send a new email."
        )
        self.mailer.send(OutgoingEmail(
            to=self.carl_email,
            subject="Re: tee time",
            body=confirm_body,
            from_address=self.bot_email,
            in_reply_to=parsed.source_message_id,
        ))

    def run_once(self) -> None:
        messages = self.inbox.fetch_unread()
        for msg in messages:
            try:
                in_reply_to = self._get_in_reply_to(msg.raw)
                if in_reply_to:
                    booking = self._find_booking_by_confirmation_id(in_reply_to)
                    if booking is not None:
                        self._handle_partner_reply(msg.raw, booking, in_reply_to=in_reply_to)
                        self.inbox.mark_seen(msg.uid)
                        continue
                # Not a partner reply — classify as cancel or request
                if parse_cancel(msg.raw):
                    self._handle_cancel(msg)
                else:
                    self._handle_request(msg)
            except Exception as e:
                self._audit("poller_error", success=False, uid=msg.uid, error=str(e))
            finally:
                self.inbox.mark_seen(msg.uid)
        self.db.execute(
            "UPDATE config SET last_poll_at=? WHERE id=1",
            (datetime.utcnow().isoformat(),),
        )
```

- [ ] **Step 4: Run tests, verify all pass**

Run: `.venv/bin/pytest tests/test_poller_orchestrator.py -v`
Expected: 4 PASS.

- [ ] **Step 5: Run full test suite**

Run: `.venv/bin/pytest -v`
Expected: ALL tests pass (~35 total).

- [ ] **Step 6: Commit**

```bash
git add src/teebot/poller_orchestrator.py tests/test_poller_orchestrator.py
git commit -m "feat(poller): IMAP loop for requests, cancels, and partner replies"
```

---

# PHASE 5: Deployment (Tasks 16–18)

Produces: executable entry points, systemd unit files, deployment + first-run docs. End state: operator follows `docs/setup.md` and has a working bot.

---

### Task 16: Entry points + systemd units

**Files:**
- Create: `scripts/run_booker.py`
- Create: `scripts/run_poller.py`
- Create: `systemd/teebot-booker.service`
- Create: `systemd/teebot-booker.timer`
- Create: `systemd/teebot-poller.service`
- Create: `systemd/teebot-poller.timer`

- [ ] **Step 1: Create the booker entry point**

`scripts/run_booker.py`:
```python
"""Entry point invoked by systemd timer at 7:58 AM Central daily."""
import sys
from datetime import date

from teebot.booker_orchestrator import BookerOrchestrator
from teebot.config import Config
from teebot.db import connect
from teebot.mailer import Mailer, OutgoingEmail


def _check_consecutive_failures(db_path: str) -> int:
    """Return the count of consecutive failed booker runs ending most-recently.
    Returns 0 if the most recent run succeeded or there are no runs.
    """
    conn = connect(db_path)
    try:
        rows = conn.execute(
            """SELECT r.status FROM requests r
                 WHERE r.status IN ('succeeded', 'failed')
                 ORDER BY r.updated_at DESC LIMIT 10"""
        ).fetchall()
    finally:
        conn.close()
    consecutive = 0
    for row in rows:
        if row["status"] == "failed":
            consecutive += 1
        else:
            break
    return consecutive


def _send_result_email(cfg: Config, mailer: Mailer, outcome) -> None:
    if outcome.skipped:
        return  # nothing to email
    if outcome.detection_signal:
        body = (
            "POSSIBLE BOT DETECTION — TeeBot has disabled itself.\n\n"
            f"Reason: {outcome.error_message}\n\n"
            "Investigate the latest audit_log rows before re-enabling.\n"
            "To re-enable: sqlite3 /var/lib/teebot/teebot.db "
            "\"UPDATE config SET bot_enabled=1\""
        )
        mailer.send(OutgoingEmail(
            to=cfg.operator_email,
            subject="⚠ TeeBot DETECTION — disabled",
            body=body,
            from_address=cfg.bot_gmail_address,
        ))
        return
    if outcome.booked_time:
        body = (
            f"Hi Carl,\n\n"
            f"You're in:\n\n"
            f"  Time:    {outcome.booked_time}\n"
            f"  Course:  {outcome.booked_course}\n"
            f"  Group:   Carl Pfiffner (you) + 3 TBD\n\n"
            f"You'll also get the official ForeTees confirmation email separately.\n\n"
            f"What do you want to do with the other 3 spots?\n\n"
            f"Reply to THIS email with one of:\n"
            f"  - \"leave open\"\n"
            f"  - \"TBD\"\n"
            f"  - \"names: Bob, Tom, Jim\""
        )
        msg_id = mailer.send(OutgoingEmail(
            to=cfg.carl_email,
            subject=f"✓ Booked - {outcome.booked_time}",
            body=body,
            from_address=cfg.bot_gmail_address,
        ))
        # Save confirmation message ID so partner replies can be threaded
        conn = connect(cfg.db_path)
        try:
            conn.execute(
                "UPDATE bookings SET confirmation_message_id=? WHERE id=?",
                (msg_id, outcome.booking_id),
            )
        finally:
            conn.close()
    else:
        body = (
            f"Hi Carl,\n\n"
            f"I tried to book but couldn't find a slot in your window today. "
            f"({outcome.attempt_count} attempts.)\n\n"
            f"You can check the tee sheet at foretees.com or send a new request "
            f"with a wider window."
        )
        mailer.send(OutgoingEmail(
            to=cfg.carl_email,
            subject="✗ Couldn't book",
            body=body,
            from_address=cfg.bot_gmail_address,
        ))


def main() -> int:
    cfg = Config.from_env()
    conn = connect(cfg.db_path)
    try:
        orch = BookerOrchestrator(
            db=conn,
            today=date.today(),
            target_offset_days=5,
            member_id="10326",
            member_name="Carl A Pfiffner",
            member_user="6605",
            foretees_username=cfg.foretees_username,
            foretees_password=cfg.foretees_password,
        )
        outcome = orch.run()
        mailer = Mailer(
            smtp_host="smtp.gmail.com", smtp_port=587,
            username=cfg.bot_gmail_address, app_password=cfg.bot_gmail_app_password,
        )
        _send_result_email(cfg, mailer, outcome)

        # Two-consecutive-failures soft alert (spec §7)
        if outcome.booked_time is None and not outcome.skipped and not outcome.detection_signal:
            consecutive = _check_consecutive_failures(cfg.db_path)
            if consecutive >= 2:
                mailer.send(OutgoingEmail(
                    to=cfg.operator_email,
                    subject=f"⚠ TeeBot {consecutive} consecutive failures",
                    body=(
                        f"TeeBot has now failed {consecutive} runs in a row.\n\n"
                        "This is a soft alert — the bot is NOT disabled. "
                        "Consider investigating audit_log and / or pausing manually.\n\n"
                        "Kill switch: sqlite3 /var/lib/teebot/teebot.db "
                        "\"UPDATE config SET bot_enabled=0\""
                    ),
                    from_address=cfg.bot_gmail_address,
                ))
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2: Create the poller entry point**

`scripts/run_poller.py`:
```python
"""Entry point invoked by systemd timer every 30s."""
import sys
from datetime import date

from teebot.config import Config
from teebot.db import connect
from teebot.inbox import Inbox
from teebot.mailer import Mailer
from teebot.poller_orchestrator import PollerOrchestrator


def main() -> int:
    cfg = Config.from_env()
    conn = connect(cfg.db_path)
    try:
        inbox = Inbox(
            host="imap.gmail.com",
            username=cfg.bot_gmail_address,
            app_password=cfg.bot_gmail_app_password,
            sender_allowlist={cfg.carl_email},
        )
        mailer = Mailer(
            smtp_host="smtp.gmail.com", smtp_port=587,
            username=cfg.bot_gmail_address, app_password=cfg.bot_gmail_app_password,
        )
        orch = PollerOrchestrator(
            db=conn,
            inbox=inbox,
            mailer=mailer,
            bot_email=cfg.bot_gmail_address,
            carl_email=cfg.carl_email,
            today=date.today(),
        )
        orch.run_once()
        inbox.close()
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 3: Create the booker systemd service unit**

`systemd/teebot-booker.service`:
```ini
[Unit]
Description=TeeBot daily 8 AM booker
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
User=teebot
Group=teebot
EnvironmentFile=/etc/teebot/secrets.env
WorkingDirectory=/opt/teebot
ExecStart=/opt/teebot/.venv/bin/python /opt/teebot/scripts/run_booker.py
StandardOutput=journal
StandardError=journal

# Failure notification
OnFailure=teebot-alert@%n.service
```

- [ ] **Step 4: Create the booker systemd timer unit**

`systemd/teebot-booker.timer`:
```ini
[Unit]
Description=Run TeeBot booker daily at 7:58 AM Central

[Timer]
OnCalendar=*-*-* 07:58:00 America/Chicago
AccuracySec=1s
Persistent=true

[Install]
WantedBy=timers.target
```

- [ ] **Step 5: Create the poller systemd service unit**

`systemd/teebot-poller.service`:
```ini
[Unit]
Description=TeeBot IMAP poller (one-shot, fires every 30s via timer)
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
User=teebot
Group=teebot
EnvironmentFile=/etc/teebot/secrets.env
WorkingDirectory=/opt/teebot
ExecStart=/opt/teebot/.venv/bin/python /opt/teebot/scripts/run_poller.py
StandardOutput=journal
StandardError=journal
```

- [ ] **Step 6: Create the poller systemd timer unit**

`systemd/teebot-poller.timer`:
```ini
[Unit]
Description=Run TeeBot poller every 30 seconds

[Timer]
OnBootSec=30s
OnUnitActiveSec=30s

[Install]
WantedBy=timers.target
```

- [ ] **Step 7: Commit**

```bash
git add scripts/run_booker.py scripts/run_poller.py systemd/
git commit -m "feat(deploy): entry points + systemd timer/service units"
```

---

### Task 17: Deployment guide + emergency runbook

**Files:**
- Create: `docs/setup.md`
- Create: `docs/EMERGENCY.md`
- Create: `scripts/kill_switch.sh`

- [ ] **Step 1: Write `docs/setup.md`**

```markdown
# TeeBot Deployment Guide

Step-by-step setup for a fresh VPS. Estimated time: ~45 minutes.

## 1. Pre-deploy: accounts

- **DigitalOcean account** (or Hetzner / Linode). Add a credit card.
- **Bot Gmail account.** Sign up for `teebotcarl@gmail.com` (or similar). Then:
  - Enable 2-step verification (required for app passwords)
  - Generate an "App password" at https://myaccount.google.com/apppasswords
    - Select app = Mail, device = "TeeBot VPS"
    - Save the 16-char password somewhere safe (you'll paste it into secrets.env later)
- **Optional: Gmail filter on Carl's `cpfiffner62@gmail.com`** to auto-forward `auto-send@foretees.com` to the bot Gmail. This enables the success cross-check (see spec §7 Phase 5).

## 2. Create the VPS

1. DigitalOcean → "Create Droplet"
2. Choose: Ubuntu 24.04 LTS, $4/mo plan (1 vCPU, 512 MB RAM), datacenter DAL or NYC1
3. Add your SSH public key (or set a root password)
4. Create the droplet, note the IP address

## 3. Initial server setup

SSH in as root:

```bash
ssh root@<IP>
```

Run:
```bash
apt update && apt upgrade -y
apt install -y python3.12 python3.12-venv git sqlite3 unattended-upgrades

# Create a non-root user for the bot
useradd -m -s /bin/bash teebot

# Create directories
mkdir -p /opt/teebot /etc/teebot /var/lib/teebot /var/log/teebot
chown teebot:teebot /opt/teebot /var/lib/teebot /var/log/teebot
chmod 700 /etc/teebot

# Enable unattended security upgrades
dpkg-reconfigure -plow unattended-upgrades
```

## 4. Clone the code and install deps

As the `teebot` user:
```bash
sudo -iu teebot
cd /opt/teebot
git clone <your-repo-url> .
python3.12 -m venv .venv
.venv/bin/pip install -e .
exit  # back to root
```

## 5. Configure secrets

As root:
```bash
cat > /etc/teebot/secrets.env <<EOF
FORETEES_USERNAME=Pfifftex
FORETEES_PASSWORD=<rotated-password-here>
BOT_GMAIL_ADDRESS=teebotcarl@gmail.com
BOT_GMAIL_APP_PASSWORD=<16-char app password>
CARL_EMAIL=cpfiffner62@gmail.com
OPERATOR_EMAIL=willpduncan@gmail.com
TIMEZONE=America/Chicago
DB_PATH=/var/lib/teebot/teebot.db
EOF
chown root:teebot /etc/teebot/secrets.env
chmod 640 /etc/teebot/secrets.env
```

⚠ **Important:** Rotate `FORETEES_PASSWORD` to a NEW value (don't reuse the one you used during development).

## 6. Initialize the database

```bash
sudo -u teebot bash -c "set -a; source /etc/teebot/secrets.env; set +a; cd /opt/teebot && .venv/bin/python scripts/init_db.py"
```

Expected output: `Initialized schema at /var/lib/teebot/teebot.db`

## 7. Install systemd units

```bash
cp /opt/teebot/systemd/teebot-*.service /etc/systemd/system/
cp /opt/teebot/systemd/teebot-*.timer /etc/systemd/system/
systemctl daemon-reload

# Enable the timers (they will fire automatically)
systemctl enable --now teebot-booker.timer
systemctl enable --now teebot-poller.timer

# Verify
systemctl list-timers | grep teebot
```

You should see both timers listed with their next-fire times.

## 8. Verify the poller is running

```bash
# Trigger one manual run
sudo -u teebot bash -c "set -a; source /etc/teebot/secrets.env; set +a; cd /opt/teebot && .venv/bin/python scripts/run_poller.py"

# Check journalctl
journalctl -u teebot-poller.service -n 50
```

## 9. Send a test request from Carl's email

From `cpfiffner62@gmail.com`, email `teebotcarl@gmail.com` with subject "tee time" and a valid request body. Wait ~60 seconds, then verify the DB:

```bash
sqlite3 /var/lib/teebot/teebot.db "SELECT * FROM requests ORDER BY id DESC LIMIT 1"
```

Confirm Carl received a confirmation email reply.

## 10. The mandatory first-run test

DO NOT rely on the bot for a competitive Monday booking until you've completed the first-run test described in spec §10.1.

Pick a low-stakes weekday afternoon, send a request, wait for the booker to fire on the corresponding morning, then have Carl cancel the resulting reservation immediately. Review `audit_log` to confirm the success-response shape.

## 11. Nightly database backup

As root, add a cron job:

```bash
cat > /etc/cron.daily/teebot-backup <<'EOF'
#!/bin/bash
set -e
mkdir -p /var/lib/teebot/backups
TS=$(date +%Y%m%d)
sqlite3 /var/lib/teebot/teebot.db ".backup /var/lib/teebot/backups/teebot-${TS}.db"
# Keep last 14 days
find /var/lib/teebot/backups -name 'teebot-*.db' -mtime +14 -delete
chown -R teebot:teebot /var/lib/teebot/backups
EOF
chmod +x /etc/cron.daily/teebot-backup

# Test it once
/etc/cron.daily/teebot-backup
ls -la /var/lib/teebot/backups/
```

Weekly off-box: copy the latest backup to your local machine (Will), e.g., via `rsync` from your laptop:

```bash
# Run this on Will's laptop, weekly
rsync -av root@<VPS-IP>:/var/lib/teebot/backups/ ~/teebot-backups/
```

## 12. (Optional) UptimeRobot

Sign up at uptimerobot.com (free). Add a "Ping" monitor for the VPS's IP. You'll get an email if the box ever goes offline.
```

- [ ] **Step 2: Write `docs/EMERGENCY.md`**

```markdown
# TeeBot Emergency Runbook

## Kill switch — disable the bot immediately

```bash
ssh root@<VPS-IP>
sqlite3 /var/lib/teebot/teebot.db "UPDATE config SET bot_enabled=0"
```

This stops all future booking attempts. The poller still runs (so Carl's emails are still acknowledged), but the booker exits immediately on its next 8 AM fire.

## Common scenarios

### "Carl just got a booking he didn't want"

He cancels manually in ForeTees:
1. pfcc.clubhouseonline-e3.com → log in → ForeTees → his name → "Tee Times" → "Make Change or View Tee Times"
2. Find the reservation → "Cancel" → confirm

### "I got a POSSIBLE DETECTION email"

1. Bot has already self-disabled (`bot_enabled=0`)
2. SSH to VPS, check the audit_log:
   ```bash
   sqlite3 /var/lib/teebot/teebot.db "SELECT timestamp, event_type, details FROM audit_log ORDER BY id DESC LIMIT 50"
   ```
3. Look for the trigger (datadome cookie, 403/429, captcha keyword)
4. Decide: pause for a week and see if DataDome stays active, or move to Approach A (browser automation — v2)

### "Booker missed the 8 AM run"

```bash
journalctl -u teebot-booker.service -n 200
systemctl list-timers | grep teebot
```

Possibilities: VPS was down, network was out, login failed (bad password). Manually rerun:
```bash
sudo -u teebot bash -c "set -a; source /etc/teebot/secrets.env; set +a; cd /opt/teebot && .venv/bin/python scripts/run_booker.py"
```

### "Carl's password changed"

Update `/etc/teebot/secrets.env`, then restart the timer:
```bash
systemctl restart teebot-booker.timer teebot-poller.timer
```

### "Bot keeps booking the wrong slot"

Most likely: the parser is misreading Carl's email. Check the latest request:
```bash
sqlite3 /var/lib/teebot/teebot.db "SELECT * FROM requests ORDER BY id DESC LIMIT 1"
```

If `course`, `window_start`, `window_end`, or `preferred_time` don't match what Carl typed, look at his email body and tighten the parser's regex.

## Re-enabling after a kill switch

Once you've investigated:
```bash
sqlite3 /var/lib/teebot/teebot.db "UPDATE config SET bot_enabled=1"
```

Then send a test request to verify everything still works.
```

- [ ] **Step 3: Create the kill-switch script**

`scripts/kill_switch.sh`:
```bash
#!/bin/bash
# Immediately disable TeeBot. Booker will skip its next fire.
# Run on the VPS as a user with read access to /etc/teebot/secrets.env

set -e

if [ -f /etc/teebot/secrets.env ]; then
    . /etc/teebot/secrets.env
fi

DB="${DB_PATH:-/var/lib/teebot/teebot.db}"

sqlite3 "$DB" "UPDATE config SET bot_enabled=0"
echo "TeeBot disabled (DB: $DB)"
echo "Audit log tail:"
sqlite3 "$DB" "SELECT timestamp, event_type, success FROM audit_log ORDER BY id DESC LIMIT 10"
```

Make it executable:
```bash
chmod +x /Users/willduncan/teebot/scripts/kill_switch.sh
```

- [ ] **Step 4: Commit**

```bash
git add docs/setup.md docs/EMERGENCY.md scripts/kill_switch.sh
git commit -m "docs(deploy): setup guide, emergency runbook, kill switch script"
```

---

### Task 18: First-run validation protocol + final smoke

**Files:**
- Create: `docs/first_run.md`
- Modify: `README.md` (add link)

- [ ] **Step 1: Write `docs/first_run.md`**

```markdown
# First-Run Validation Protocol

Before relying on TeeBot for a competitive Monday booking, you MUST complete this controlled live test once. This validates the success-response shape and trains Carl on the manual-cancel path.

## Step 1: Pick a low-stakes target

Choose a **Tuesday afternoon ~5-6 days out** where Pine Forest has wide availability and zero demand pressure. Example: Tuesday at 3:00 PM on the Green course.

## Step 2: Carl sends the request

From `cpfiffner62@gmail.com`, email `teebotcarl@gmail.com`:

```
Subject: tee time

Day: Tuesday <date>
Course: Green
Window: 2:30 PM to 4:00 PM
Preferred: 3:00 PM
```

Wait for the confirmation reply (within ~60s). Verify it matches what was sent.

## Step 3: Wait for the booker fire

On the **morning 5 days before the target day**, the booker fires at 7:58 AM Central. Watch via SSH:

```bash
ssh root@<VPS-IP>
journalctl -u teebot-booker.service -f
```

You should see auth, warm hold, race, slot attempts. The whole sequence takes ~30-60 seconds.

## Step 4: Verify the booking exists

After the booker emails Carl success:

1. Carl logs into ForeTees and confirms the reservation is visible under his name at the booked time/course.
2. Will (operator) inspects the audit log:
   ```bash
   sqlite3 /var/lib/teebot/teebot.db "SELECT timestamp, event_type, details FROM audit_log WHERE timestamp >= datetime('now', '-1 hour') ORDER BY id"
   ```
3. Note the `booking_attempted` row and the success-response body in `details`. This is the canonical success format we'll trust going forward.

## Step 5: Carl cancels the test reservation immediately

Within 10 minutes:
1. pfcc.clubhouseonline-e3.com → ForeTees → his name → "Tee Times" → "Make Change or View Tee Times"
2. Find the test reservation → click Cancel → confirm
3. Verify the slot is released

## Step 6: Sign off

In `docs/first_run.md`, add a line below recording the test outcome:

```
- Test booking 2026-MM-DD: <success/failure>. Booking latency XXXms. Success-response confirmed at audit_log.id=NNNN.
```

The bot is then cleared for competitive Monday use.

## If the test fails

- Booker errored out → check journalctl, fix the issue, repeat the test.
- Booking succeeded but no email arrived → SMTP issue, check `mailer.py` / app password.
- Booking succeeded but DB shows `failure` → response-shape mismatch in `submit_booking`, update the success heuristic in `src/teebot/foretees/booker.py`.
- Slot wasn't actually reserved in ForeTees → false-positive success classifier, same fix.

## Sign-off log

(append test results here as they happen)
```

- [ ] **Step 2: Update README**

Edit `/Users/willduncan/teebot/README.md` — replace the bullet list with:

```markdown
## Quick reference
- Spec: [docs/specs/2026-05-15-foretees-bot-design.md](docs/specs/2026-05-15-foretees-bot-design.md)
- Implementation plan: [docs/plans/2026-05-15-teebot-implementation.md](docs/plans/2026-05-15-teebot-implementation.md)
- Deployment: [docs/setup.md](docs/setup.md)
- First-run protocol: [docs/first_run.md](docs/first_run.md)
- Emergency runbook: [docs/EMERGENCY.md](docs/EMERGENCY.md)
```

- [ ] **Step 3: Run the full test suite one final time**

Run: `cd /Users/willduncan/teebot && .venv/bin/pytest -v`
Expected: all tests pass.

- [ ] **Step 4: Commit**

```bash
git add docs/first_run.md README.md
git commit -m "docs(first-run): validation protocol; README pointers"
```

---

## Final Summary

After Task 18, the codebase contains:
- A working Python package (`teebot`) with ~10 focused modules
- Comprehensive tests (~35) — all passing
- systemd units for both the daily booker and the 30s poller
- Deployment guide, emergency runbook, and first-run protocol
- A spec doc that traces every implementation choice

**Next steps (operator, not in this plan):**
1. Stand up the VPS following `docs/setup.md`
2. Send a test request from Carl's email
3. Execute the first-run validation per `docs/first_run.md`
4. After clean first-run → start using for real Monday bookings
5. After first month → review audit_log; if zero detection signals, consider building the v2 Playwright fallback for resilience
