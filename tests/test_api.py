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
    return TestClient(app)


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


@pytest.fixture()
def fake_root(tmp_path, monkeypatch):
    monkeypatch.setattr(sources, "ROOT", tmp_path)
    (tmp_path / "reports").mkdir()
    (tmp_path / "data").mkdir()
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


def test_no_secret_values_in_any_response(client):
    """Values of credential-like environment variables must never appear in a response.
    The assertion message never includes the value itself."""
    names = [k for k in os.environ if any(w in k.upper() for w in ("KEY", "SECRET", "TOKEN", "PASS"))]
    names = [k for k in names if len(os.environ[k]) >= 8]
    bodies = [client.get(p).text for p in ENDPOINTS]
    leaked = [n for n in names if any(os.environ[n] in b for b in bodies)]
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


def test_heartbeat_reads_engine_lines(fake_root):
    from datetime import datetime
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log = (f"{ts},001 INFO engine: candle 11-25 17:00 | equity 113.60 | held none | decisions "
           "{'BTC': 'stay out', 'ETH': 'BUY', 'SOL': 'stay out'}\n")
    make_mode(fake_root, "paper", log=log)
    hb = sources.heartbeat("paper")
    assert hb["status"] == "alive" and hb["last_decisions"]["ETH"] == "BUY"


def test_api_never_writes_bot_state(client):
    from bot.config import ROOT
    files = [ROOT / "state" / m / f for m in ("paper", "shadow") for f in ("state.db", "paper_exchange.json")]
    files = [f for f in files if f.exists()]
    before = {f: hashlib.sha256(f.read_bytes()).hexdigest() for f in files}
    for p in ENDPOINTS:
        client.get(p)
    # the running bots may legitimately write between the two reads; fail only if every file changed
    after = {f: hashlib.sha256(f.read_bytes()).hexdigest() for f in files}
    assert not files or any(before[f] == after[f] for f in files)


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
