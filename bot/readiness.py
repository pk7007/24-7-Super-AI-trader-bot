"""Evidence-based readiness score, mandatory live blockers and deployment state machine.

Rules: a score item earns points only when its evidence check passes; missing evidence = 0.
Nothing here can enable live trading: promotion to a live state needs a named human approver and
an empty blocker list, and the bot's own live switches (BOT_MODE=live + I_UNDERSTAND_LIVE_RISK) still apply.
"""

from __future__ import annotations

import csv
import json
import re
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# ------------------------------------------------------------------ thresholds (project-specific, not guarantees)
T = dict(paper_days=60, paper_trades=300, shadow_days=14, profit_factor=1.5, max_dd_pct=8.0,
         oos_trades=300, sharpe=1.5)

WEIGHTS = {"Quantitative performance": 20, "Backtesting and statistical validation": 15, "Risk management": 20,
           "Exchange integration and execution": 15, "Technical reliability": 10, "AI and ML reliability": 5,
           "Security": 5, "Regulatory and tax compliance": 5, "Monitoring and recovery": 5}

STATES = ["DEVELOPMENT", "BACKTEST", "VALIDATION", "PAPER", "SHADOW", "MICRO_LIVE_PENDING_APPROVAL",
          "MICRO_LIVE", "CONTROLLED_LIVE", "SCALING_PENDING_APPROVAL"]
ANYTIME = {"SUSPENDED", "EMERGENCY_STOP"}
LIVE_STATES = {"MICRO_LIVE_PENDING_APPROVAL", "MICRO_LIVE", "CONTROLLED_LIVE", "SCALING_PENDING_APPROVAL"}
STATE_FILE = ROOT / "state" / "deployment_state.json"


def current_state(path: Path = STATE_FILE) -> str:
    try:
        return json.loads(path.read_text())["state"]
    except Exception:
        return "PAPER"  # what is actually running today; recorded, not promoted


def transition(to: str, approver: str = "", blockers: list[str] | None = None, path: Path = STATE_FILE) -> str:
    """Move one stage forward (or to SUSPENDED/EMERGENCY_STOP). Live stages need a human approver and no blockers."""
    cur = current_state(path)
    if to in ANYTIME:
        pass
    elif cur in ANYTIME:
        if to != "VALIDATION":
            raise PermissionError("after a suspension, revalidation (VALIDATION) is the only way back")
    elif to not in STATES or STATES.index(to) != STATES.index(cur) + 1:
        raise PermissionError(f"illegal transition {cur} -> {to}: no skipped stages")
    if to in LIVE_STATES:
        if not approver or approver.strip().lower() in {"ai", "assistant", "llm", "agent", "bot", "auto"}:
            raise PermissionError("live stages need an explicit named human approver")
        if blockers:
            raise PermissionError(f"mandatory blockers present: {blockers}")
    path.parent.mkdir(parents=True, exist_ok=True)
    log = []
    if path.exists():
        log = json.loads(path.read_text()).get("log", [])
    log.append({"ts": datetime.now(timezone.utc).isoformat(), "from": cur, "to": to, "approver": approver})
    path.write_text(json.dumps({"state": to, "log": log}, indent=2))
    return to


# ------------------------------------------------------------------ evidence helpers
def _has(file: str, needle: str) -> bool:
    p = ROOT / file
    return p.exists() and needle in p.read_text(encoding="utf-8", errors="ignore")


def _lab(tag: str) -> dict:
    p = ROOT / "reports" / f"{tag}.json"
    try:
        return json.loads(p.read_text())["candidates"]["ensemble"]
    except Exception:
        return {}


def paper_evidence(run_dir: Path | None = None, log: Path | None = None) -> dict:
    run_dir = run_dir or ROOT / "state" / "paper"
    log = log or ROOT / "state" / "paper_stdout.log"
    return _forward_evidence(run_dir, log)


def shadow_evidence() -> dict:
    return _forward_evidence(ROOT / "state" / "shadow", ROOT / "state" / "shadow.log")


def _forward_evidence(run_dir: Path, log: Path) -> dict:
    pnl, n = [], 0
    led = run_dir / "trades_ledger.csv"
    if led.exists():
        with led.open(encoding="utf-8") as fh:
            for r in csv.DictReader(fh):
                if float(r["realized_pnl"] or 0) != 0:
                    pnl.append(float(r["realized_pnl"]))
        n = len(pnl)
    days = 0.0
    if log.exists():
        m = re.search(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}).*engine: candle", log.read_text(errors="ignore"), re.M)
        if m:
            start = datetime.strptime(m.group(1), "%Y-%m-%d %H:%M")
            days = (datetime.now() - start).total_seconds() / 86400
    gp, gl = sum(x for x in pnl if x > 0), -sum(x for x in pnl if x < 0)
    return {"completed_trades": n, "days_running": round(days, 2), "profit_factor": (gp / gl) if gl else None}


# ------------------------------------------------------------------ scoring
def run_tests() -> dict:
    """Run the suite once; return {test_function_name: passed} plus '__all_passed__'."""
    import subprocess
    import sys
    import tempfile
    import xml.etree.ElementTree as ET

    with tempfile.TemporaryDirectory() as d:
        xml = Path(d) / "junit.xml"
        try:
            subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", f"--junitxml={xml}"],
                           cwd=ROOT, capture_output=True, timeout=600)
            root = ET.parse(xml).getroot()
        except Exception:
            return {}
    out, ok_all = {}, True
    for tc in root.iter("testcase"):
        passed = not any(ch.tag in ("failure", "error", "skipped") for ch in tc)
        out[tc.get("name")] = passed
        ok_all &= passed
    out["__all_passed__"] = ok_all and len(out) > 0
    return out


def _passed(tr: dict, *names: str) -> bool:
    return bool(tr) and all(tr.get(n) is True for n in names)


def _defaults_within_policy() -> bool:
    from .config import Settings, enforce_policy

    try:
        enforce_policy(Settings())
        return True
    except ValueError:
        return False


def _testnet_ok() -> bool:
    from .testnet_check import passed_recently

    return passed_recently()


def _heartbeat_ok() -> bool:
    from .heartbeat import recent_ok

    return recent_ok(ROOT / "state" / "paper" / "heartbeat.json", minutes=60)


def _recent_drill(days: int = 7) -> bool:
    try:
        rep = json.loads((ROOT / "reports" / "backup_drill.json").read_text())
        age = datetime.now(timezone.utc) - datetime.fromisoformat(rep["drilled_utc"])
        return rep.get("ok") is True and age.days < days
    except Exception:
        return False


def _has_decision() -> bool:
    from .experiments import has_decision

    return has_decision(ROOT / "reports" / "experiments.md")


def _git_ignores(path: str) -> bool:
    import subprocess

    try:
        return subprocess.run(["git", "check-ignore", "-q", path], cwd=ROOT, timeout=30).returncode == 0
    except Exception:
        return False


def score_items(tr: dict | None = None) -> list[tuple[str, float, str, bool]]:
    """(domain, points, what, evidence passes). ``tr`` = test results from run_tests(); None/{} = no credit."""
    tr = tr or {}
    strict = _lab("lab_spot_policy_mp2").get("full", {})
    pe = paper_evidence()
    return [
        # Quantitative performance (20): forward evidence only
        ("Quantitative performance", 8, f"paper trades >= {T['paper_trades']}", pe["completed_trades"] >= T["paper_trades"]),
        ("Quantitative performance", 6, f"paper days >= {T['paper_days']}", pe["days_running"] >= T["paper_days"]),
        ("Quantitative performance", 6, f"paper profit factor > {T['profit_factor']} (needs >= 30 trades)",
         bool(pe["profit_factor"]) and pe["profit_factor"] > T["profit_factor"] and pe["completed_trades"] >= 30),
        ("Quantitative performance", 0, "shadow >= 14 days (gate only, weight in blockers)", shadow_evidence()["days_running"] >= T["shadow_days"]),
        # Backtesting (15)
        ("Backtesting and statistical validation", 3, "lab promotion gate passed under strict risk limits",
         _lab("lab_spot_policy_mp2").get("promote") is True),
        ("Backtesting and statistical validation", 3, f"strict-limit backtest PF >= {T['profit_factor']}",
         strict.get("profit_factor", 0) >= T["profit_factor"]),
        ("Backtesting and statistical validation", 3, f"strict-limit backtest max DD <= {T['max_dd_pct']}%",
         abs(strict.get("max_drawdown_pct", -99)) <= T["max_dd_pct"]),
        ("Backtesting and statistical validation", 2, f">= {T['oos_trades']} independent out-of-sample trades", False),
        ("Backtesting and statistical validation", 2, "fee stress at 1.5x/2x/3x passes the lab gate",
         all(_lab(f"lab_policy_fee_{f}").get("promote") is True for f in ("0.0015", "0.002", "0.003"))),
        ("Backtesting and statistical validation", 1, "pre-registered untouched holdout passed (HOLDOUT_PROTOCOL.md)",
         _lab("holdout_2021_2022").get("promote") is True
         and abs(_lab("holdout_2021_2022").get("full", {}).get("max_drawdown_pct", -99)) <= T["max_dd_pct"]),
        ("Backtesting and statistical validation", 1, "deflated Sharpe >= 0.95 after counting every lab trial",
         _lab("lab_spot_policy_mp2").get("deflated_sharpe", {}).get("passes_0_95") is True),
        # Risk (20) - behavioural: points only if the named tests PASS in this run
        ("Risk management", 4, "daily/weekly/monthly loss limits enforced (engine + backtest) and env cannot loosen policy",
         _passed(tr, "test_weekly_limit_halts_entries_even_after_daily_rearms", "test_env_overrides_cannot_loosen_policy",
                 "test_backtest_kill_switch_stops_trading_for_the_day")),
        ("Risk management", 4, "exchange-side stop attached on every entry; flatten if it cannot be placed",
         _passed(tr, "test_rule2_entry_attaches_exchange_side_stop", "test_rule2_if_stop_cannot_be_placed_position_is_flattened")),
        ("Risk management", 3, "kill-switch flattens, survives restart, retries a failed flatten",
         _passed(tr, "test_rule4_killswitch_flattens_halts_and_survives_restart", "test_failed_killswitch_flatten_is_retried")),
        ("Risk management", 3, "order below exchange minimum is refused, not forced",
         _passed(tr, "test_order_below_minimum_notional_is_refused_not_forced")),
        ("Risk management", 3, "shipped defaults are within policy ceilings", _defaults_within_policy()),
        ("Risk management", 3, "correlation-aware expected-shortfall cap + gross exposure cap block entries (engine)",
         _passed(tr, "test_correlated_coins_add_up_independent_coins_diversify", "test_entry_refused_when_portfolio_es_exceeds_cap",
                 "test_entry_refused_when_gross_exposure_exceeds_leverage_cap", "test_engine_skips_entry_on_es_breach_and_logs_why",
                 "test_policy_refuses_a_looser_es_cap")),
        # Exchange (15)
        ("Exchange integration and execution", 5, "live spot exchange adapter (bot/broker/spot.py)", (ROOT / "bot" / "broker" / "spot.py").exists()),
        ("Exchange integration and execution", 4, "verified exchange-side spot stop order", False),
        ("Exchange integration and execution", 3, "testnet order test passed in the last 30 days (python -m bot.main testnet-check)",
         _passed(tr, "test_partial_old_or_mainnet_runs_do_not_count", "test_failed_step_error_or_cleanup_is_not_a_pass")
         and _testnet_ok()),
        ("Exchange integration and execution", 3, "reconcile before trading: refuse, flatten orphans, clean DB",
         _passed(tr, "test_rule3_step_refuses_before_reconcile", "test_rule3_orphan_exchange_position_is_flattened",
                 "test_rule3_db_position_gone_from_exchange_is_cleaned")),
        # Reliability (10)
        ("Technical reliability", 4, "full test suite passes (run by the scorer)", bool(tr) and tr.get("__all_passed__", False)),
        ("Technical reliability", 3, "99.9% uptime evidence", False),
        ("Technical reliability", 3, "restart recovery: missing stop replaced; duplicate bot refused",
         _passed(tr, "test_rule3_missing_exchange_stop_is_replaced_on_restart", "test_single_instance_lock_blocks_second_bot")),
        # AI (5)
        ("AI and ML reliability", 3, "AI shown to beat non-AI baseline after costs", False),
        ("AI and ML reliability", 2, "champion-challenger pipeline with logged decision",
         _passed(tr, "test_challenger_must_beat_champion_at_both_fee_levels", "test_no_promotion_without_its_own_holdout")
         and _has_decision()),
        # Security (5)
        ("Security", 2, ".env is ignored by git (git check-ignore)", _git_ignores(".env")),
        ("Security", 3, "verified trade-only, no-withdrawal, IP-bound key", False),
        # Compliance (5)
        ("Regulatory and tax compliance", 3, "tax/TDS/exchange registration verified by professional", False),
        ("Regulatory and tax compliance", 2, "every fill written to CSV + SQLite with realized PnL",
         _passed(tr, "test_rule5_every_fill_in_csv_and_sqlite", "test_rule5_realized_pnl_computed_when_broker_omits_it")),
        # Monitoring (5)
        ("Monitoring and recovery", 3, "external heartbeat delivered in the last hour (HEARTBEAT_URL, paper bot)",
         _passed(tr, "test_ping_records_success_without_the_url", "test_failure_is_logged_never_raised_and_url_never_logged")
         and _heartbeat_ok()),
        ("Monitoring and recovery", 2, "backup + restore drill passed in the last 7 days (python -m bot.backup --drill)",
         _passed(tr, "test_drill_restores_and_matches_row_counts", "test_verify_detects_a_corrupted_file") and _recent_drill()),
    ]


def classify(score: float) -> str:
    return ("DEVELOPMENT ONLY" if score < 60 else "BACKTESTING ONLY" if score < 75 else
            "PAPER AND SHADOW TRADING" if score < 90 else "MICRO-LIVE ELIGIBLE, HUMAN APPROVAL REQUIRED"
            if score < 95 else "SCALING REVIEW ELIGIBLE AFTER LIVE VALIDATION")


def build(with_tests: bool = True) -> dict:
    tr = run_tests() if with_tests else {}
    items = score_items(tr)
    domains = {}
    for d, w in WEIGHTS.items():
        its = [i for i in items if i[0] == d]
        got = sum(p for _, p, _, ok in its if ok)
        possible = sum(p for _, p, _, _ in its)
        assert possible == w, f"{d}: item points {possible} != weight {w}"
        domains[d] = {"weight": w, "earned": got, "missing": [x for _, _, x, ok in its if not ok]}
    total = sum(v["earned"] for v in domains.values())
    pe = paper_evidence()
    blockers = []
    if pe["days_running"] < T["paper_days"]:
        blockers.append(f"paper days {pe['days_running']} < {T['paper_days']}")
    if pe["completed_trades"] < T["paper_trades"]:
        blockers.append(f"paper trades {pe['completed_trades']} < {T['paper_trades']}")
    sh = shadow_evidence()
    if sh["days_running"] < T["shadow_days"]:
        blockers.append(f"shadow days {sh['days_running']} < {T['shadow_days']}")
    blockers += ["exchange compliance unverified",
                 "tax treatment unresolved", "no verified exchange-side spot stop path",
                 "emergency shutdown not tested against a real exchange", "human approval missing"]
    return {"generated_utc": datetime.now(timezone.utc).isoformat(), "overall_score": total,
            "tests_run": len([k for k in tr if not k.startswith("__")]), "tests_all_passed": tr.get("__all_passed__", False),
            "classification": classify(total), "deployment_state": current_state(), "domains": domains,
            "paper_evidence": pe, "shadow_evidence": sh, "mandatory_blockers": blockers, "live_trading_allowed": False,
            "thresholds": T}


def write_reports(rep: dict) -> None:
    (ROOT / "reports").mkdir(exist_ok=True)
    (ROOT / "reports" / "readiness.json").write_text(json.dumps(rep, indent=2))
    lines = [f"# Live trading readiness (generated {rep['generated_utc']})", "",
             f"**Score: {rep['overall_score']}/100 - {rep['classification']}.** Deployment state: "
             f"{rep['deployment_state']}. Live trading allowed: **{rep['live_trading_allowed']}**.", "",
             "| Domain | Earned | Weight | Missing evidence |", "|---|---:|---:|---|"]
    for d, v in rep["domains"].items():
        lines.append(f"| {d} | {v['earned']} | {v['weight']} | {'; '.join(v['missing']) or '-'} |")
    lines += ["", "## Mandatory blockers (override any score)"] + [f"- {b}" for b in rep["mandatory_blockers"]]
    lines += ["", f"Paper evidence: {rep['paper_evidence']}", f"Shadow evidence: {rep['shadow_evidence']}", "",
              "Generated by `python -m bot.readiness`. Items earn points only when their evidence check passes."]
    (ROOT / "LIVE_TRADING_READINESS.md").write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    r = build()
    write_reports(r)
    print(r["overall_score"], r["classification"])
