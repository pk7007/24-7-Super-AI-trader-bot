import pytest

from bot import readiness as r


def test_no_skipped_stages(tmp_path):
    f = tmp_path / "s.json"
    assert r.current_state(f) == "PAPER"
    with pytest.raises(PermissionError):
        r.transition("MICRO_LIVE", "alice", [], f)
    assert r.transition("SHADOW", "", [], f) == "SHADOW"


def test_live_needs_human_and_no_blockers(tmp_path):
    f = tmp_path / "s.json"
    r.transition("SHADOW", "", [], f)
    with pytest.raises(PermissionError):
        r.transition("MICRO_LIVE_PENDING_APPROVAL", "assistant", [], f)
    with pytest.raises(PermissionError):
        r.transition("MICRO_LIVE_PENDING_APPROVAL", "alice", ["paper days short"], f)
    assert r.transition("MICRO_LIVE_PENDING_APPROVAL", "alice", [], f) == "MICRO_LIVE_PENDING_APPROVAL"


def test_suspension_only_returns_via_validation(tmp_path):
    f = tmp_path / "s.json"
    r.transition("EMERGENCY_STOP", "", [], f)
    with pytest.raises(PermissionError):
        r.transition("PAPER", "", [], f)
    assert r.transition("VALIDATION", "", [], f) == "VALIDATION"


def test_score_weights_and_live_never_allowed_without_evidence():
    rep = r.build(with_tests=False)  # no recursion into pytest; test-backed items get no credit
    assert sum(v["weight"] for v in rep["domains"].values()) == 100
    assert rep["live_trading_allowed"] is False and rep["mandatory_blockers"]
    assert rep["overall_score"] < 60


def test_old_lot_model_reports_cannot_earn_current_readiness_points(tmp_path, monkeypatch):
    import json
    from bot.backtest import SIMULATION_VERSION
    monkeypatch.setattr(r, "ROOT", tmp_path)
    (tmp_path / "reports").mkdir()
    path = tmp_path / "reports" / "lab_spot_policy_mp2.json"
    report = {"candidates": {"ensemble": {"promote": True}}}
    path.write_text(json.dumps(report))
    assert r._lab("lab_spot_policy_mp2") == {}
    report["simulation_version"] = SIMULATION_VERSION
    path.write_text(json.dumps(report))
    assert r._lab("lab_spot_policy_mp2")["promote"] is True


def test_nonzero_pytest_exit_cannot_pass_with_partial_green_xml(monkeypatch):
    import subprocess
    from pathlib import Path
    from types import SimpleNamespace

    def failed_run(args, **kwargs):
        xml = next(value.split("=", 1)[1] for value in args if value.startswith("--junitxml="))
        Path(xml).write_text('<testsuites><testsuite><testcase name="partial"/></testsuite></testsuites>')
        return SimpleNamespace(returncode=2)

    monkeypatch.setattr(subprocess, "run", failed_run)
    assert not r.run_tests().get("__all_passed__", False)
