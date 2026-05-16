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
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

# Bootstrap import paths so `teebot` (in src/) and sibling scripts are importable
# without requiring `pip install`. Works in any deployment context.
_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT / "src"))
sys.path.insert(0, str(_ROOT / "scripts"))

from run_booker import main as booker_main
from run_poller import main as poller_main

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
log = logging.getLogger("teebot.daemon")

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

    while True:
        # Always run the poller (cheap, handles errors internally)
        try:
            poller_main()
        except Exception:
            log.exception("Poller iteration failed")

        # Check booker fire window
        now = datetime.now(CHICAGO)
        today = now.date()
        if last_booker_date != today and _in_booker_window(now):
            try:
                log.info("Firing booker at %s (Central)", now.isoformat())
                booker_main()
                last_booker_date = today
            except Exception:
                log.exception("Booker iteration failed")
                # Still mark as fired so we don't retry on next poll loop;
                # operator must investigate via audit_log + emergency runbook
                last_booker_date = today

        time.sleep(POLL_INTERVAL_SEC)


if __name__ == "__main__":
    sys.exit(main() or 0)
