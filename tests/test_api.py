"""Observational API: read-only, typed envelope, missing != zero, mode isolation, no secret exposure."""

import hashlib
import json
import os
import sqlite3

import pytest
from fastapi.testclient import TestClient

from bot.api import sources
from bot.api.app import app

ENDPOINTS = ["/api/v1/overview", "/api/v1/positions", "/api/v1/fills", "/api/v1/signals", "/api/v1/intents",
             "/api/v1/risk", "/api/v1/strategies", "/api/v1/backtests", "/api/v1/readiness", "/api/v1/ledger",
             "/api/v1/health", "/api/v1/events", "/api/v1/candles?source=cached", "/api/v1/feasibility"]


@pytest.fixture()
def client():
    return TestClient(app, base_url="http://127.0.0.1")


def make_mode(root, mode, cash=113.6, positions=(), fills=(), halted="0", log=None):
    d = root / "state" / mode
    d.mkdir(parents=True, exist_ok=True)
    (d / "paper_exchange.json").write_text(json.dumps({"cash": cash, "positions": {}, "stops": {}}))
    con = sqlite3.connect(d / "state.db")
    con.executescript(
        "CREATE TABLE positions (symbol TEXT PRIMARY KEY, side INTEGER, contracts REAL, entry REAL, stop REAL,"
        " stop_id TEXT, opened_ts TEXT); CREATE TABLE fills (id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT, symbol TEXT,"
        " side TEXT, qty REAL, price REAL, fee REAL, realized_pnl REAL, reason TEXT, order_id TEXT);"
        " CREATE TABLE kv (key TEXT PRIMARY KEY, value TEXT);")
    con.execute("INSERT INTO kv VALUES ('ks_halted', ?)", (halted,))
    con.execute("INSERT INTO kv VALUES ('ks_start', '120.0')")
    for p in positions:
        con.execute("INSERT INTO positions VALUES (?,?,?,?,?,?,?)", p)
    for f in fills:
        con.execute("INSERT INTO fills (ts,symbol,side,qty,price,fee,realized_pnl,reason,order_id) "
                    "VALUES (?,?,?,?,?,?,?,?,?)", f)
    con.commit()
    con.close()
    if log is not None:
        (root / "state" / f"{mode}.log").write_text(log)
    return d


@pytest.fixture(autouse=True)
def fake_root(tmp_path, monkeypatch):
    monkeypatch.setattr(sources, "ROOT", tmp_path)
    (tmp_path / "reports").mkdir()
    (tmp_path / "data").mkdir()
    (tmp_path / "reports" / "backtest_equity.csv").write_text("date,equity\n2026-01-01,100\n")
    return tmp_path


def test_every_endpoint_returns_the_envelope(client):
    for path in ENDPOINTS:
        r = client.get(path)
        assert r.status_code == 200, path
        body = r.json()
        assert body["schema_version"] == "1.0" and body["observed_utc"] and "data" in body, path
        assert "NaN" not in r.text and "Infinity" not in r.text, path


@pytest.mark.parametrize("method", ["post", "put", "patch", "delete"])
def test_writes_are_refused(client, method):
    assert getattr(client, method)("/api/v1/overview").status_code == 405


@pytest.mark.parametrize("path", ["/api/v1/positions?mode=live", "/api/v1/candles?symbol=DOGE",
                                  "/api/v1/candles?limit=999999", "/api/v1/events?mode=../../etc"])
def test_inputs_are_whitelisted(client, path):
    assert client.get(path).status_code == 422


def test_no_path_traversal_through_the_spa_route(client):
    r = client.get("/..%2F..%2Fbot%2Fconfig.py")
    assert "POLICY_CEILING" not in r.text


def test_security_headers(client):
    r = client.get("/api/v1/risk")
    assert r.headers["x-content-type-options"] == "nosniff" and r.headers["cache-control"] == "no-store"


def test_no_secret_values_in_any_response(client, monkeypatch):
    """Values of credential-like environment variables must never appear in a response.
    The assertion message never includes the value itself."""
    names = {"DELTA_API_KEY": "fixture-key-no-exposure", "DELTA_API_SECRET": "fixture-secret-no-exposure",
             "TELEGRAM_BOT_TOKEN": "fixture-token-no-exposure"}
    for name, value in names.items():
        monkeypatch.setenv(name, value)
    bodies = [client.get(p).text for p in ENDPOINTS]
    leaked = [n for n, value in names.items() if any(value in b for b in bodies)]
    assert not leaked, f"secret env values exposed for: {leaked}"
    for b in bodies:
        assert "TELEGRAM_BOT_TOKEN" not in b and "DELTA_API" not in b


def test_empty_state_is_missing_not_zero(fake_root):
    o = sources.mode_overview("paper")
    assert o["equity"]["value"] is None and o["equity"]["availability"] == "missing"
    assert o["open_positions"] is None and o["realized_pnl"] is None and o["entries_halted"] is None
    assert o["heartbeat"]["status"] == "unknown"
    assert sources.ledger_rows("paper")["availability"].startswith("missing")


def test_modes_are_isolated(fake_root):
    make_mode(fake_root, "paper", cash=100.0, positions=[("BTC/USD:USD", 1, 30, 95000.0, 90000.0, "P1", "t")])
    make_mode(fake_root, "shadow", cash=200.0)
    p, sh = sources.mode_overview("paper"), sources.mode_overview("shadow")
    assert p["equity"]["value"] == 100.0 and sh["equity"]["value"] == 200.0
    assert p["open_positions"] == 1 and sh["open_positions"] == 0
    pos = sources.positions("paper")["rows"][0]
    assert pos["coins"] == pytest.approx(30 * 0.00001) and pos["side_label"] == "LONG"  # engine units -> coins


def test_kill_switch_and_utilization(fake_root):
    make_mode(fake_root, "paper", cash=118.8, halted="1")
    ks = sources.mode_overview("paper")["kill_switches"]["daily"]
    assert ks["halted"] is True and ks["drawdown_pct"] == pytest.approx(-1.0)
    assert ks["utilization_pct"] == pytest.approx(100.0)


def test_accounting_safety_halt_is_visible_in_overview(fake_root):
    directory = make_mode(fake_root, "paper")
    with sqlite3.connect(directory / "state.db") as con:
        con.execute("INSERT INTO kv VALUES ('safety_accounting_halted', '1')")
    overview = sources.mode_overview("paper")
    assert overview["accounting_halted"] is True and overview["entries_halted"] is True


def test_heartbeat_reads_engine_lines(fake_root):
    from datetime import datetime, timezone
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log = (f"{ts},001 INFO engine: candle 11-25 17:00 | equity 113.60 | held none | decisions "
           "{'BTC': 'stay out', 'ETH': 'BUY', 'SOL': 'stay out'}\n"
           f"{ts},002 INFO engine: step complete candle {datetime.now(timezone.utc).isoformat()}\n")
    make_mode(fake_root, "paper", log=log)
    hb = sources.heartbeat("paper")
    assert hb["status"] == "alive" and hb["last_decisions"]["ETH"] == "BUY"


def test_api_never_writes_bot_state(client, fake_root):
    make_mode(fake_root, "paper")
    make_mode(fake_root, "shadow")
    ROOT = sources.ROOT
    files = [ROOT / "state" / m / f for m in ("paper", "shadow") for f in ("state.db", "paper_exchange.json")]
    files = [f for f in files if f.exists()]
    before = {f: hashlib.sha256(f.read_bytes()).hexdigest() for f in files}
    for p in ENDPOINTS:
        client.get(p)
    after = {f: hashlib.sha256(f.read_bytes()).hexdigest() for f in files}
    assert before == after


def test_strategies_mark_lightgbm_rejected(client):
    rows = client.get("/api/v1/strategies").json()["data"]["rows"]
    assert next(r for r in rows if r["id"] == "lightgbm")["status"] == "REJECTED"


def test_historical_backtest_is_labelled_as_looser_risk(client):
    eq = client.get("/api/v1/backtests").json()["data"]["historical_equity"]
    assert "NOT the current policy" in eq["classification"]


def test_no_protection_claims_live_verification(client):
    """No live venue is connected, so nothing may be presented as verified on a real exchange."""
    prots = client.get("/api/v1/risk").json()["data"]["protections"]
    assert prots and all("verified_live" not in p for p in prots)
    for p in prots:
        v = p["verified_by"].lower()
        assert "live" not in v or "needs a live venue" in v or "never" in v, p


def test_readiness_thresholds_come_from_the_source(client):
    from bot import readiness
    d = client.get("/api/v1/readiness").json()["data"]
    assert d["thresholds"] == readiness.T and d["states"] == readiness.STATES


@pytest.mark.parametrize("host", ["attacker.example", "localhost.attacker.example", "127.0.0.1.attacker.example"])
def test_nonlocal_host_is_rejected_before_reading_state(client, monkeypatch, host):
    monkeypatch.setattr(sources, "db_read", lambda *a: pytest.fail("state read for an untrusted host"))
    assert client.get("/api/v1/fills", headers={"host": host}).status_code == 400


@pytest.mark.parametrize("host", ["127.0.0.1:8765", "localhost:8765", "[::1]:8765"])
def test_explicit_local_hosts_are_allowed(client, host):
    assert client.get("/api/v1/fills", headers={"host": host}).status_code == 200


def test_api_settings_do_not_modify_environment_or_load_dotenv(monkeypatch):
    from bot import config
    monkeypatch.setattr(config, "load_env", lambda *a, **k: pytest.fail("dashboard read dotenv"))
    monkeypatch.setenv("BOT_MODE", "live")
    before = dict(os.environ)
    assert sources.run_cfg("paper").mode == "paper"
    assert sources.run_cfg("shadow").mode == "shadow"
    assert dict(os.environ) == before
    risk = sources.risk_view()
    assert risk["runtime_configuration_verified"] is False
    assert "inferred" in risk["configuration_source"]


def test_old_report_cannot_be_labelled_current_policy(fake_root):
    report = {"candidates": {"ensemble": {"effective_config": {"risk_per_trade": 0.005, "max_positions": 2}, "promote": True}}}
    assert sources._classify_report(report) != "current policy"
    (fake_root / "reports" / "lab_spot_policy_mp2.json").write_text(json.dumps(report))
    ensemble = next(row for row in sources.strategies()["rows"] if row["id"] == "ensemble")
    assert ensemble["evidence_policy"] != "current policy" and "running" not in ensemble["status"]


def test_missing_strategy_evidence_is_unknown_not_rejected_or_running(fake_root):
    rows = sources.strategies()["rows"]
    assert all(row["status"] == "not evaluated" for row in rows if row["id"] != "lightgbm")


@pytest.mark.parametrize("message,secret", [
    ("request api_key=fixture-key-123 failed", "fixture-key-123"),
    ('headers {"DELTA_API_SECRET": "fixture-secret-123"}', "fixture-secret-123"),
    ("Authorization: Bearer fixture-bearer-123", "fixture-bearer-123"),
    ("https://api.telegram.org/bot123456:fixture-telegram-123/sendMessage", "fixture-telegram-123"),
    ("https://example.test/data?signature=fixture-signature-123&symbol=BTC", "fixture-signature-123"),
])
def test_event_messages_redact_credential_patterns(fake_root, message, secret):
    from datetime import datetime
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    make_mode(fake_root, "paper", log=f"{ts},001 ERROR main: {message}\n")
    event = sources.events("paper")[0]
    assert secret not in event["message"] and "[REDACTED]" in event["message"]


def test_overview_totals_include_fills_beyond_display_limit(fake_root):
    fills = [("2026-01-01", "BTC/USD:USD", "sell", 1, 100, 0, 1, "exit", str(i)) for i in range(1001)]
    make_mode(fake_root, "paper", fills=fills)
    overview = sources.mode_overview("paper")
    assert overview["fill_count"] == 1001 and overview["realized_pnl"] == 1001


@pytest.mark.parametrize("kind,offset", [("diagnostic", 0), ("completion", 60), ("old completion", -60)])
def test_heartbeat_requires_a_recent_completed_step(fake_root, kind, offset):
    from datetime import datetime, timedelta, timezone
    ts = (datetime.now() + timedelta(minutes=offset)).strftime("%Y-%m-%d %H:%M:%S")
    message = ("candle 11-28 12:00 | equity 113.60 | held none | decisions {}" if kind == "diagnostic" else
               "step complete candle " + (datetime.now(timezone.utc) + timedelta(minutes=offset)).isoformat())
    make_mode(fake_root, "paper", log=f"{ts},001 INFO engine: {message}\n")
    assert sources.heartbeat("paper")["status"] != "alive"


def test_relogging_an_old_completed_candle_does_not_restore_health(fake_root):
    from datetime import datetime, timedelta, timezone
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    old = (datetime.now(timezone.utc) - timedelta(hours=3)).isoformat()
    make_mode(fake_root, "paper", log=f"{ts},001 INFO engine: step complete candle {old}\n")
    assert sources.heartbeat("paper")["status"] == "stale"


def test_health_coverage_counts_unique_completed_steps_not_diagnostics(fake_root):
    from datetime import datetime, timezone
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    candle = datetime.now(timezone.utc).isoformat()
    complete = f"{stamp},002 INFO engine: step complete candle {candle}\n"
    diagnostic = f"{stamp},001 INFO engine: candle 11-28 12:00 | equity 113.60 | held none | decisions {{}}\n"
    make_mode(fake_root, "paper", log=diagnostic * 3 + complete * 2)
    assert sources.health()["modes"]["paper"]["candles_last_24h"] == 1


def test_partial_candidate_configuration_is_not_current_policy():
    from bot.backtest import SIMULATION_VERSION
    report = {"simulation_version": SIMULATION_VERSION, "market": "spot", "allow_short": False,
              "candidates": {"ensemble": {"effective_config": dict(sources.POLICY)}, "unknown": {}}}
    assert sources._classify_report(report) != "current policy"
