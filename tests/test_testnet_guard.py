import json
from datetime import datetime, timedelta, timezone

import pytest

from bot.config import MAINNET_API, TESTNET_API, Settings
from bot.testnet_check import EXPECTED_STEPS, Checklist, TestnetOnly, guard, passed_recently, write_report


def full_checklist(fail: str | None = None) -> Checklist:
    cl = Checklist()
    for name in EXPECTED_STEPS:
        cl.check(name, name != fail, "evidence")
    return cl


def test_report_records_every_step_and_no_secrets(tmp_path, monkeypatch):
    monkeypatch.setenv("DELTA_API_KEY", "KEY123")
    monkeypatch.setenv("DELTA_API_SECRET", "SECRET456")
    p = write_report(full_checklist(), Settings(testnet=True), cleanup_ok=True, path=tmp_path / "t.json")
    rep = json.loads(p.read_text())
    assert rep["all_passed"] and rep["endpoint"] == TESTNET_API and len(rep["steps"]) == len(EXPECTED_STEPS)
    assert "KEY123" not in p.read_text() and "SECRET456" not in p.read_text()
    assert passed_recently(p)


def test_failed_step_error_or_cleanup_is_not_a_pass(tmp_path):
    s = Settings(testnet=True)
    assert not passed_recently(write_report(full_checklist(fail="stop cancelled"), s, True, path=tmp_path / "a.json"))
    assert not passed_recently(write_report(full_checklist(), s, True, error=RuntimeError("x"), path=tmp_path / "b.json"))
    assert not passed_recently(write_report(full_checklist(), s, False, path=tmp_path / "c.json"))


def test_partial_old_or_mainnet_runs_do_not_count(tmp_path):
    p = write_report(full_checklist(), Settings(testnet=True), True, path=tmp_path / "t.json")
    rep = json.loads(p.read_text())
    for change in ({"steps": rep["steps"][:5]}, {"endpoint": MAINNET_API},
                   {"ran_utc": (datetime.now(timezone.utc) - timedelta(days=31)).isoformat()}):
        p.write_text(json.dumps({**rep, **change}))
        assert not passed_recently(p), change
    assert not passed_recently(tmp_path / "missing.json")


def test_testnet_check_refuses_mainnet(monkeypatch):
    monkeypatch.setenv("DELTA_TESTNET", "0")
    with pytest.raises(TestnetOnly):
        guard(Settings(testnet=False))


def test_testnet_check_needs_live_consent(monkeypatch):
    from bot.broker.delta import LiveTradingNotAllowed

    monkeypatch.setenv("DELTA_TESTNET", "1")
    monkeypatch.setenv("BOT_MODE", "paper")
    monkeypatch.delenv("I_UNDERSTAND_LIVE_RISK", raising=False)
    with pytest.raises(LiveTradingNotAllowed):
        guard(Settings(testnet=True))
