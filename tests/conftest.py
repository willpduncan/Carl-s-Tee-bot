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
