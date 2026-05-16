"""Long-running daemon entry point for Railway / Fly.io / any PaaS.

Polls Carl's bot Gmail every ~30 seconds for new emails, and fires the
booker daily at 7:58 AM Central. Single process, single container.

The booker is idempotent: if it fires twice on the same day, the second
fire finds status != 'pending' and exits cleanly. So a restart mid-morning
won't double-book.
"""
import logging
import os
import sys
import time
from datetime import date, datetime, time as dtime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

# Bootstrap import paths so `teebot` (in src/) and sibling scripts are importable
# without requiring `pip install`. Works in any deployment context.
_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT / "src"))
sys.path.insert(0, str(_ROOT / "scripts"))

from run_booker import _send_result_email, main as booker_main
from run_poller import main as poller_main
from teebot.booker_orchestrator import BookerOrchestrator
from teebot.config import Config
from teebot.db import connect, init_schema
from teebot.mailer import Mailer

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
log = logging.getLogger("teebot.daemon")


def _ensure_db_initialized() -> None:
    """Idempotently create the SQLite schema. Safe to call on every boot —
    init_schema uses CREATE TABLE IF NOT EXISTS."""
    cfg = Config.from_env()
    conn = connect(cfg.db_path)
    try:
        init_schema(conn)
        log.info("Database ready at %s", cfg.db_path)
    finally:
        conn.close()


def _book_immediately_for_open_dates(cfg: Config) -> None:
    """For any pending request whose target_date is already inside the 5-day
    open window, fire the booker right now (skipping warm-hold + race-wait).
    """
    tz = ZoneInfo(cfg.timezone)
    today = datetime.now(tz).date()
    earliest = today + timedelta(days=1)
    latest = today + timedelta(days=5)

    conn = connect(cfg.db_path)
    try:
        rows = conn.execute(
            """SELECT target_date, status FROM requests
                 WHERE status = 'pending'
                   AND target_date BETWEEN ? AND ?
                 ORDER BY target_date""",
            (earliest.isoformat(), latest.isoformat()),
        ).fetchall()
        # Diagnostic: also show all pending rows regardless of date
        all_pending = conn.execute(
            "SELECT target_date FROM requests WHERE status = 'pending'"
        ).fetchall()
    finally:
        conn.close()

    log.info(
        "Immediate-book check: today=%s window=[%s, %s] in-window pending=%d "
        "all pending=%s",
        today, earliest, latest, len(rows),
        [r["target_date"] for r in all_pending],
    )

    if not rows:
        return

    for row in rows:
        target_date = date.fromisoformat(row["target_date"])
        offset = (target_date - today).days
        log.info("Auto-booking already-open date %s (offset=%d)",
                 target_date, offset)
        _run_immediate_booker(cfg, offset, today, tz)


def _run_immediate_booker(cfg: Config, offset: int, today: date,
                          tz: ZoneInfo) -> None:
    """Run the booker for a specific offset right now, with race_at = now
    so warm_hold and wait_until_T0 collapse to no-ops."""
    conn = connect(cfg.db_path)
    try:
        now_local = datetime.now(tz)
        race_now = dtime(now_local.hour, now_local.minute, now_local.second)
        orch = BookerOrchestrator(
            db=conn,
            today=today,
            target_offset_days=offset,
            member_id="10326",
            member_name="Carl A Pfiffner",
            member_user="6605",
            foretees_username=cfg.foretees_username,
            foretees_password=cfg.foretees_password,
            tz=cfg.timezone,
            race_at_local_time=race_now,
        )
        outcome = orch.run()
        mailer = Mailer(
            api_key=cfg.sendgrid_api_key,
            from_email=cfg.bot_gmail_address,
            from_name="Carl's Tee Bot",
        )
        _send_result_email(cfg, mailer, outcome)
    finally:
        conn.close()

CHICAGO = ZoneInfo("America/Chicago")

# Fire booker between 7:58:00 and 7:59:59 Central. The booker's internal
# _wait_until_T0 then holds until 8:00:00.000 for the race phase.
BOOKER_FIRE_HOUR = 7
BOOKER_FIRE_MINUTE_MIN = 58
BOOKER_FIRE_MINUTE_MAX = 60  # exclusive — i.e., minute < 60

POLL_INTERVAL_SEC = 30


def _in_booker_window(now: datetime) -> bool:
    return (
        now.hour == BOOKER_FIRE_HOUR
        and BOOKER_FIRE_MINUTE_MIN <= now.minute < BOOKER_FIRE_MINUTE_MAX
    )


def main() -> int:
    last_booker_date: date | None = None
    log.info("Daemon starting — poll every %ds, booker window 7:58–7:59 Central",
             POLL_INTERVAL_SEC)
    _ensure_db_initialized()

    while True:
        # Always run the poller (cheap, handles errors internally)
        try:
            poller_main()
        except Exception:
            log.exception("Poller iteration failed")

        # Auto-book any pending requests for dates already in the open window
        try:
            cfg = Config.from_env()
            _book_immediately_for_open_dates(cfg)
        except Exception:
            log.exception("Immediate-book iteration failed")

        # Check booker fire window (the 8 AM race for tomorrow-opening dates)
        now = datetime.now(CHICAGO)
        today = now.date()
        if last_booker_date != today and _in_booker_window(now):
            try:
                log.info("Firing booker at %s (Central)", now.isoformat())
                booker_main()
                last_booker_date = today
            except Exception:
                log.exception("Booker iteration failed")
                last_booker_date = today

        time.sleep(POLL_INTERVAL_SEC)


if __name__ == "__main__":
    sys.exit(main() or 0)
