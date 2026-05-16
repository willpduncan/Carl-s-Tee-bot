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
