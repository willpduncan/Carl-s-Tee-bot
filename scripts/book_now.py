"""One-off: attempt to book a specific date immediately.

Bypasses the 7:58 AM warm-hold and 8:00:00.000 race phases by setting
the race target to "now" — every timing check sees its deadline as
already past and returns instantly. Auth, tee-sheet fetch, slot-form
fetch, booking submit, and result email all run normally.

Use for:
  - Tonight's end-to-end dry-run against real ForeTees
  - Same-week bookings for dates already within the 5-day open window

Usage (via Railway CLI):
    railway run python scripts/book_now.py YYYY-MM-DD

A *pending* request matching the target date must already exist in the
DB (i.e., Carl already emailed his preferences for that date).
"""
import sys
from datetime import date, datetime, time as dtime
from pathlib import Path
from zoneinfo import ZoneInfo

# Bootstrap import paths
_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT / "src"))
sys.path.insert(0, str(_ROOT / "scripts"))

from teebot.booker_orchestrator import BookerOrchestrator
from teebot.config import Config
from teebot.db import connect
from teebot.mailer import Mailer, OutgoingEmail
from run_booker import _send_result_email  # reuse the result-email helper


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(f"Usage: {sys.argv[0]} YYYY-MM-DD")
        return 2
    try:
        target = date.fromisoformat(argv[1])
    except ValueError:
        print(f"Invalid date: {argv[1]!r}. Use YYYY-MM-DD.")
        return 2

    today = date.today()
    offset = (target - today).days
    if offset < 1:
        print(f"Target {target} is in the past or today (offset={offset}). Aborting.")
        return 2
    if offset > 5:
        print(
            f"Target {target} is {offset} days out, beyond the 5-day open window. "
            "ForeTees won't allow booking yet."
        )
        return 2

    cfg = Config.from_env()
    conn = connect(cfg.db_path)
    try:
        # Race-at = now in local TZ → warm_hold + wait_until_T0 collapse to no-ops
        now_local = datetime.now(ZoneInfo(cfg.timezone))
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

        print(f"\n=== Outcome ===")
        print(f"skipped: {outcome.skipped} (reason: {outcome.skipped_reason!r})")
        print(f"booked: {outcome.booked_time} {outcome.booked_course}")
        print(f"reservation_id: {outcome.booked_reservation_id}")
        print(f"attempts: {outcome.attempt_count}")
        print(f"detection_signal: {outcome.detection_signal}")
        print(f"error: {outcome.error_message!r}")
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main(sys.argv))
