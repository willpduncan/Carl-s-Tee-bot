"""Entry point invoked by systemd timer every 30s."""
import sys
from datetime import date
from pathlib import Path

# Bootstrap import path: make `teebot` (in ../src) importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

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
