"""Idempotently initialize the teebot SQLite database."""
import sys
from pathlib import Path

# Bootstrap import path: make `teebot` (in ../src) importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

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
