from datetime import datetime, timedelta, timezone

import pytest

from bot import healthcheck
from bot.api import sources


@pytest.mark.parametrize("kind,minutes,expected", [("complete", 1, True), ("error", 0, False),
                                                  ("complete", 50, False), ("no data", 1, False),
                                                  ("complete", -10, False), ("diagnostic", 0, False)])
def test_health_requires_a_recent_successful_candle(tmp_path, monkeypatch, kind, minutes, expected):
    monkeypatch.setattr(sources, "ROOT", tmp_path)
    (tmp_path / "state").mkdir()
    ts = (datetime.now() - timedelta(minutes=minutes)).strftime("%Y-%m-%d %H:%M:%S")
    if kind == "error":
        message = "monitor failed"
    elif kind == "complete":
        message = "step complete candle " + (datetime.now(timezone.utc) - timedelta(minutes=minutes)).isoformat()
    else:
        message = "candle 11-28 07:00 | equity 113.60 | held none | decisions " + ("no data" if kind == "no data" else "{}")
    (tmp_path / "state" / "paper.log").write_text(f"{ts},001 ERROR engine: {message}\n")
    assert healthcheck.healthy("paper") is expected


def test_completed_wait_without_entry_decisions_is_healthy(tmp_path, monkeypatch):
    monkeypatch.setattr(sources, "ROOT", tmp_path)
    (tmp_path / "state").mkdir()
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    now = datetime.now(timezone.utc).isoformat()
    (tmp_path / "state/paper.log").write_text(
        f"{ts},001 INFO engine: candle 11-28 07:00 | equity 113.60 | held BTC | decisions no data\n"
        f"{ts},002 INFO engine: step complete candle {now}\n")
    assert healthcheck.healthy("paper") is True
