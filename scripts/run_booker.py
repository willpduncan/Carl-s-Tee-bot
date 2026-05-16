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
        return
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

        # Two-consecutive-failures soft alert
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
