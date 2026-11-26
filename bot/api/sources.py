"""Read-only readers for the observational API. No function here writes anything.

Every reader returns plain dicts. "Missing" is reported as ``None`` plus an ``availability`` string, never as 0.
"""

from __future__ import annotations

import csv
import json
import math
import os
import re
import sqlite3
import time
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from pathlib import Path

from ..config import POLICY_CEILING, ROOT, Settings

MODES = ("paper", "shadow")
SYMBOLS = ("BTC", "ETH", "SOL")
HEARTBEAT_MAX_MIN = 40  # the Compose healthcheck threshold (operational), not market-data freshness
LOG_LINE = re.compile(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}),\d+ (\w+) (\w+): (.*)$")
CANDLE_LINE = re.compile(r"candle (\d{2}-\d{2} \d{2}:\d{2}) \| equity ([\d.]+) \| held (.*?) \| decisions (.*)$")


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def iso(dt: datetime | None) -> str | None:
    return dt.astimezone(timezone.utc).isoformat(timespec="seconds") if dt else None


def run_cfg(mode: str = "paper") -> Settings:
    """The settings the running bots use: same env as run_bot.cmd / docker-compose (ensemble, spot)."""
    os.environ.setdefault("STRATEGY", "ensemble")
    os.environ.setdefault("MARKET", "spot")
    os.environ["BOT_MODE"] = mode
    return Settings.from_env()


def bot_symbol(cfg: Settings, base: str) -> str:
    return next(s for s in cfg.symbols if s.split("/")[0] == base)


# ------------------------------------------------------------------ files
def _local_tz():
    return datetime.now().astimezone().tzinfo


def read_log(mode: str, max_lines: int = 4000) -> list[dict]:
    """Parse state/<mode>.log (local-time stamps from the bot's logging) into dicts with UTC times."""
    p = ROOT / "state" / f"{mode}.log"
    if not p.exists():
        return []
    with p.open("rb") as fh:  # read only the tail: logs grow forever
        fh.seek(0, 2)
        size = fh.tell()
        fh.seek(max(0, size - 600_000))
        lines = fh.read().decode("utf-8", errors="replace").splitlines()[-max_lines:]
    out, tz = [], _local_tz()
    for ln in lines:
        m = LOG_LINE.match(ln)
        if not m:
            continue
        ts = datetime.strptime(m.group(1), "%Y-%m-%d %H:%M:%S").replace(tzinfo=tz)
        out.append({"ts": ts, "level": m.group(2), "logger": m.group(3), "message": m.group(4)})
    return out


def candle_events(mode: str) -> list[dict]:
    """The engine's per-candle heartbeat lines: equity, holdings and each coin's decision."""
    out = []
    for e in read_log(mode):
        if e["logger"] != "engine":
            continue
        m = CANDLE_LINE.search(e["message"])
        if not m:
            continue
        raw = m.group(4)
        try:
            decisions = json.loads(raw.replace("'", '"')) if raw.startswith("{") else {}
        except ValueError:
            decisions = {}
        out.append({"logged_utc": iso(e["ts"]), "candle_label_utc": m.group(1), "equity": float(m.group(2)),
                    "held": m.group(3), "decisions": decisions, "no_data": raw == "no data"})
    return out


def paper_account(mode: str) -> dict:
    p = ROOT / "state" / mode / "paper_exchange.json"
    if not p.exists():
        return {"availability": "missing", "cash": None, "positions": {}, "source": str(p.relative_to(ROOT))}
    try:
        s = json.loads(p.read_text(encoding="utf-8"))
        return {"availability": "ok", "cash": float(s["cash"]), "positions": s.get("positions", {}),
                "updated_utc": iso(datetime.fromtimestamp(p.stat().st_mtime, timezone.utc)),
                "source": str(p.relative_to(ROOT))}
    except Exception as e:  # noqa: BLE001
        return {"availability": f"unreadable: {type(e).__name__}", "cash": None, "positions": {},
                "source": str(p.relative_to(ROOT))}


def _ro(db: Path) -> sqlite3.Connection:
    con = sqlite3.connect(f"file:{db.as_posix()}?mode=ro", uri=True, timeout=5)
    con.row_factory = sqlite3.Row
    return con


def db_read(mode: str) -> dict:
    """Positions, fills and kill-switch keys from state.db, opened read-only (the engine keeps writing)."""
    db = ROOT / "state" / mode / "state.db"
    res = {"availability": "missing", "positions": [], "fills": [], "kv": {}, "source": f"state/{mode}/state.db"}
    if not db.exists():
        return res
    try:
        con = _ro(db)
        try:
            res["positions"] = [dict(r) for r in con.execute("SELECT * FROM positions")]
            res["fills"] = [dict(r) for r in con.execute("SELECT * FROM fills ORDER BY id DESC LIMIT 1000")]
            res["kv"] = {r["key"]: r["value"] for r in con.execute("SELECT key, value FROM kv")}
        finally:
            con.close()
        res["availability"] = "ok"
    except Exception as e:  # noqa: BLE001
        res["availability"] = f"unreadable: {type(e).__name__}"
    return res


def ledger_rows(mode: str) -> dict:
    p = ROOT / "state" / mode / "trades_ledger.csv"
    if not p.exists():
        return {"availability": "missing (no fills yet: the ledger file is created on the first fill)",
                "rows": [], "source": f"state/{mode}/trades_ledger.csv"}
    with p.open(newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    return {"availability": "ok", "rows": rows, "source": f"state/{mode}/trades_ledger.csv"}


def shadow_intents() -> dict:
    p = ROOT / "state" / "shadow" / "shadow_intents.csv"
    if not p.exists():
        return {"availability": "missing (no order intention yet: written on the first shadow signal)",
                "rows": [], "source": "state/shadow/shadow_intents.csv"}
    with p.open(newline="", encoding="utf-8") as fh:
        return {"availability": "ok", "rows": list(csv.DictReader(fh))[-500:], "source": "state/shadow/shadow_intents.csv"}


# ------------------------------------------------------------------ derived views
def _switch(kv: dict, prefix: str, limit: float, equity: float | None) -> dict:
    start = kv.get(f"{prefix}_start")
    try:
        start_f = float(start) if start is not None else None
    except ValueError:
        start_f = None
    dd = (equity / start_f - 1) if (equity is not None and start_f and start_f > 0) else None
    return {"period": kv.get(f"{prefix}_day"), "start_equity": start_f, "limit_pct": limit * 100,
            "drawdown_pct": round(dd * 100, 4) if dd is not None else None,
            "utilization_pct": round(max(0.0, -dd) / limit * 100, 2) if dd is not None else None,
            "halted": {"1": True, "0": False}.get(kv.get(f"{prefix}_halted"))}


def heartbeat(mode: str) -> dict:
    ev = candle_events(mode)
    last = ev[-1] if ev else None
    if not last:
        return {"status": "unknown", "last_candle_logged_utc": None, "age_min": None, "threshold_min": HEARTBEAT_MAX_MIN}
    ts = datetime.fromisoformat(last["logged_utc"])
    age = (now_utc() - ts).total_seconds() / 60
    return {"status": "alive" if age <= HEARTBEAT_MAX_MIN else "stale", "last_candle_logged_utc": last["logged_utc"],
            "age_min": round(age, 1), "threshold_min": HEARTBEAT_MAX_MIN,
            "last_decisions": last["decisions"], "last_no_data": last["no_data"]}


def mode_overview(mode: str) -> dict:
    cfg = run_cfg(mode)
    acct, db = paper_account(mode), db_read(mode)
    eq = acct["cash"]
    kv = db["kv"]
    switches = {"daily": _switch(kv, "ks", cfg.daily_loss_limit, eq),
                "weekly": _switch(kv, "ksw", cfg.weekly_loss_limit, eq),
                "monthly": _switch(kv, "ksm", cfg.monthly_loss_limit, eq)}
    fills = db["fills"]
    realized = sum(float(f["realized_pnl"]) for f in fills) if db["availability"] == "ok" else None
    open_risk = sum(abs(p["entry"] - p["stop"]) * p["contracts"] * _unit(p["symbol"], cfg) for p in db["positions"])
    return {
        "mode": mode, "simulated": True,
        "heartbeat": heartbeat(mode),
        "equity": {"value": eq, "currency": "USD", "basis": "paper cash (open positions valued at entry)",
                   "start_equity": cfg.start_equity, "availability": acct["availability"],
                   "updated_utc": acct.get("updated_utc")},
        "realized_pnl": realized, "fill_count": len(fills) if db["availability"] == "ok" else None,
        "open_positions": len(db["positions"]) if db["availability"] == "ok" else None,
        "open_risk_usd": round(open_risk, 6) if db["availability"] == "ok" else None,
        "kill_switches": switches,
        "entries_halted": any(s["halted"] for s in switches.values()) if db["availability"] == "ok" else None,
        "db_availability": db["availability"],
    }


def _unit(symbol: str, cfg: Settings) -> float:
    from ..riskcheck import coin_units
    try:
        return coin_units(symbol, cfg.market)
    except KeyError:
        return float("nan")


def positions(mode: str) -> dict:
    cfg = run_cfg(mode)
    db = db_read(mode)
    rows = []
    for p in db["positions"]:
        u = _unit(p["symbol"], cfg)
        coins = p["contracts"] * u
        rows.append({**p, "coins": coins, "notional_usd": coins * p["entry"],
                     "risk_to_stop_usd": abs(p["entry"] - p["stop"]) * coins,
                     "side_label": {1: "LONG", -1: "SHORT"}.get(p["side"], "INVALID")})
    return {"availability": db["availability"], "rows": rows, "source": db["source"],
            "note": "contracts are the engine's units (lot steps on spot); coins = contracts x lot step"}


def risk_view() -> dict:
    cfg = run_cfg("paper")
    eff = {k: getattr(cfg, k) for k in ("risk_per_trade", "max_positions", "daily_loss_limit", "weekly_loss_limit",
                                        "monthly_loss_limit", "max_leverage", "stop_atr", "min_order_inr",
                                        "max_venue_deviation", "taker_fee", "gst", "slippage", "stop_slippage",
                                        "usdt_inr", "market", "allow_short", "strategy", "start_equity")}
    discrepancies = []
    if POLICY_CEILING["daily_loss_limit"] != cfg.daily_loss_limit:
        discrepancies.append(
            f"daily loss: configured default {cfg.daily_loss_limit:.0%} vs policy ceiling "
            f"{POLICY_CEILING['daily_loss_limit']:.0%} (an env override may loosen it up to the ceiling). "
            "Project safety rule 4 names 3%; the master prompts set 1%. Human review needed.")
    from ..risk import round_trip_cost_pct
    return {"effective": eff, "policy_ceiling": POLICY_CEILING, "discrepancies": discrepancies,
            "round_trip_cost_pct": round(round_trip_cost_pct(cfg) * 100, 4),
            "protections": [
                {"name": "Exchange-side stop on every entry", "status": "enforced in engine (paper broker simulates it)",
                 "verified_by": "unit tests + paper simulation; never on a real exchange"},
                {"name": "Stale-data guard", "status": "enforced: a coin is skipped when its last candle is not the expected one",
                 "verified_by": "unit tests + running paper bot"},
                {"name": "Venue price deviation guard", "status": f"configured {cfg.max_venue_deviation:.1%}; active only with a venue price feed (live)",
                 "verified_by": "not active yet (needs a live venue)"},
                {"name": "Kill-switches (daily / weekly / monthly)", "status": "persisted in state.db; flatten retried every tick",
                 "verified_by": "unit tests; never triggered in paper"},
                {"name": "Single-instance lock", "status": "state/<mode>/bot.lock", "verified_by": "running paper and shadow bots"},
                {"name": "Minimum economic order", "status": f"Rs {cfg.min_order_inr:.0f} (ASSUMPTION, verify per exchange)",
                 "verified_by": "assumption, not verified"},
            ],
            "modes": {m: mode_overview(m)["kill_switches"] for m in MODES}}


# ------------------------------------------------------------------ reports
POLICY = dict(risk_per_trade=0.005, max_positions=2)


def _classify_report(d: dict) -> str:
    cands = d.get("candidates", {})
    cfgs = [c.get("effective_config") for c in cands.values() if c.get("effective_config")]
    if not cfgs:
        return "historical: risk settings not recorded (pre-2026-11-24, mostly 1% risk / 3 positions)"
    if all(c["risk_per_trade"] <= POLICY["risk_per_trade"] and c["max_positions"] <= POLICY["max_positions"] for c in cfgs):
        return "current policy"
    return "looser than current policy"


def lab_reports() -> list[dict]:
    out = []
    for p in sorted((ROOT / "reports").glob("*.json")):
        if p.name in ("readiness.json", "skills_audit.json", "backtest_metrics.json", "replay_summary.json"):
            continue
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            continue
        if "candidates" not in d:
            continue
        out.append({"tag": p.stem, "window": d.get("window"), "market": d.get("market"), "taker_fee": d.get("taker_fee"),
                    "classification": _classify_report(d), "buy_and_hold_pct": d.get("buy_and_hold_pct"),
                    "candidates": d["candidates"],
                    "generated_utc": iso(datetime.fromtimestamp(p.stat().st_mtime, timezone.utc))})
    return out


def strategies() -> dict:
    """Strategy registry from real artefacts. Status comes from the lab gate in the current-policy report and,
    for the ML model, from MODEL_EVALUATION.md."""
    rep = next((r for r in lab_reports() if r["tag"] == "lab_spot_policy_mp2"), None)
    base = next((r for r in lab_reports() if r["tag"] == "lab_spot"), None)
    rows = []
    for name, label in (("ensemble", "Ensemble (EMA trend + time-series momentum)"), ("trend_ema", "EMA trend"),
                        ("tsmom", "Time-series momentum"), ("donchian", "Donchian breakout")):
        cur = (rep or {}).get("candidates", {}).get(name)
        old = (base or {}).get("candidates", {}).get(name)
        src = cur or old
        rows.append({"id": name, "label": label,
                     "status": ("PAPER (running, promoted by lab gate)" if name == "ensemble" else
                                ("passed gate (not deployed)" if src and src.get("promote") else "rejected by lab gate")),
                     "evidence_tag": "lab_spot_policy_mp2" if cur else ("lab_spot" if old else None),
                     "evidence_policy": "current policy" if cur else "historical (looser risk)",
                     "metrics": src.get("full") if src else None,
                     "monte_carlo": src.get("monte_carlo") if src else None,
                     "subperiod_returns_pct": src.get("subperiod_returns_pct") if src else None,
                     "rejected_because": src.get("rejected_because") if src else None})
    rows.append({"id": "lightgbm", "label": "LightGBM 3-class model", "status": "REJECTED",
                 "evidence_tag": "MODEL_EVALUATION.md", "evidence_policy": "historical",
                 "metrics": None, "monte_carlo": None, "subperiod_returns_pct": None,
                 "rejected_because": ["did not beat a no-model baseline after costs; independent FreqAI run -15.7%, PF 0.46"]})
    return {"rows": rows}


def readiness() -> dict:
    from .. import readiness as r
    p = ROOT / "reports" / "readiness.json"
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
        avail = "ok"
    except Exception as e:  # noqa: BLE001
        d, avail = {}, f"unreadable: {type(e).__name__}"
    return {"availability": avail, "report": d, "thresholds": r.T, "weights": r.WEIGHTS, "states": r.STATES,
            "anytime_states": sorted(r.ANYTIME), "live_states": sorted(r.LIVE_STATES),
            "current_state": r.current_state(), "source": "reports/readiness.json + bot/readiness.py",
            "note": "Trading readiness, scored by bot/readiness.py. Unrelated to frontend quality."}


def backtest_equity(max_points: int = 1500) -> dict:
    p = ROOT / "reports" / "backtest_equity.csv"
    m = ROOT / "reports" / "backtest_metrics.json"
    if not p.exists():
        return {"availability": "missing", "points": []}
    rows = list(csv.reader(p.open(encoding="utf-8")))[1:]
    step = max(1, len(rows) // max_points)
    pts = [{"t": r[0], "equity": float(r[1])} for r in rows[::step] if len(r) > 1]
    peak, dd = 0.0, []
    for x in pts:
        peak = max(peak, x["equity"])
        dd.append({"t": x["t"], "drawdown_pct": round((x["equity"] / peak - 1) * 100, 3) if peak else None})
    return {"availability": "ok", "points": pts, "drawdown": dd,
            "metrics": json.loads(m.read_text()) if m.exists() else None,
            "classification": "historical: looser risk (1% per trade, 3 positions, perp-era settings). NOT the current policy",
            "generated_utc": iso(datetime.fromtimestamp(p.stat().st_mtime, timezone.utc))}


@lru_cache(maxsize=1)
def _feasibility_cached(day: str) -> dict:
    import pandas as pd

    from ..feasibility import Assumptions, build_report
    cfg = run_cfg("paper")
    p = ROOT / "data" / "BTC_15m_binance.csv"
    btc = pd.read_csv(p, index_col=0, parse_dates=True)
    rows, text = build_report(cfg, btc, Assumptions())
    a = Assumptions()
    return {"rows": rows, "assumptions": {k: getattr(a, k) for k in a.__dataclass_fields__},
            "usdt_inr": cfg.usdt_inr, "fees": {"taker": cfg.taker_fee, "gst": cfg.gst, "slippage": cfg.slippage},
            "data": f"cached Binance BTC/USDT 15m to {btc.index[-1]}", "markdown": text}


def feasibility() -> dict:
    try:
        return {"availability": "ok", **_feasibility_cached(now_utc().strftime("%Y-%m-%d"))}
    except Exception as e:  # noqa: BLE001
        return {"availability": f"unavailable: {type(e).__name__}: {e}", "rows": []}


# ------------------------------------------------------------------ candles
_CANDLE_CACHE: dict[tuple, tuple[float, dict]] = {}


def candles(base: str, limit: int = 300, source: str = "live") -> dict:
    """15m candles. live = public Binance (cached 30 s); cached = the local data/*_binance.csv file."""
    cfg = run_cfg("paper")
    sym = bot_symbol(cfg, base)
    key = (base, limit, source)
    hit = _CANDLE_CACHE.get(key)
    if hit and time.time() - hit[0] < 30:
        return hit[1]
    tf = timedelta(minutes=cfg.tf_minutes)
    res: dict
    if source == "live":
        try:
            from ..data import make_reference_exchange, source_symbol
            ex = make_reference_exchange()
            rows = ex.fetch_ohlcv(source_symbol(cfg, sym), cfg.timeframe, limit=limit)
            bars = [{"t": int(r[0] / 1000), "o": r[1], "h": r[2], "l": r[3], "c": r[4], "v": r[5]} for r in rows]
            res = {"availability": "ok", "source": f"live: Binance public {source_symbol(cfg, sym)} 15m", "bars": bars}
        except Exception as e:  # noqa: BLE001
            res = {"availability": f"live unavailable: {type(e).__name__}", "source": "live", "bars": []}
    else:
        p = ROOT / "data" / f"{base}_15m_binance.csv"
        if not p.exists():
            res = {"availability": "missing", "source": "cached", "bars": []}
        else:
            with p.open("rb") as fh:
                fh.seek(0, 2)
                fh.seek(max(0, fh.tell() - limit * 90))
                tail = fh.read().decode("utf-8", errors="replace").splitlines()[1:][-limit:]
            bars = []
            for ln in tail:
                parts = ln.split(",")
                if len(parts) != 6:
                    continue
                t = datetime.fromisoformat(parts[0])
                bars.append({"t": int(t.timestamp()), "o": float(parts[1]), "h": float(parts[2]), "l": float(parts[3]),
                             "c": float(parts[4]), "v": float(parts[5])})
            res = {"availability": "ok", "source": f"cached: {p.relative_to(ROOT).as_posix()} (not live)", "bars": bars}
    now = now_utc().timestamp()
    for b in res["bars"]:
        b["closed"] = b["t"] + tf.total_seconds() <= now
    res.update({"symbol": base, "signal_pair": f"{base}/USDT (Binance)", "execution_instrument": sym,
                "timeframe": cfg.timeframe, "observed_utc": iso(now_utc())})
    if res["bars"]:
        last_closed = next((b for b in reversed(res["bars"]) if b["closed"]), None)
        res["last_closed_utc"] = iso(datetime.fromtimestamp(last_closed["t"], timezone.utc)) if last_closed else None
        res["data_age_min"] = round((now - last_closed["t"] - tf.total_seconds()) / 60, 1) if last_closed else None
    _CANDLE_CACHE[key] = (time.time(), res)
    return res


# ------------------------------------------------------------------ health / events
def events(mode: str, limit: int = 200) -> list[dict]:
    out = [{"ts_utc": iso(e["ts"]), "level": e["level"], "logger": e["logger"], "message": e["message"][:400]}
           for e in read_log(mode) if not (e["logger"] == "engine" and e["message"].startswith("candle "))]
    return out[-limit:][::-1]


def health() -> dict:
    out = {}
    for m in MODES:
        log = ROOT / "state" / f"{m}.log"
        ev = read_log(m)
        day_ago = now_utc() - timedelta(hours=24)
        recent = [e for e in ev if e["ts"] >= day_ago]
        candles_24h = [e for e in recent if e["logger"] == "engine" and e["message"].startswith("candle ")]
        db = db_read(m)
        starts = [iso(e["ts"]) for e in ev if "entering main loop" in e["message"]]
        out[m] = {
            "heartbeat": heartbeat(m),
            "log": {"exists": log.exists(), "size_kb": round(log.stat().st_size / 1024, 1) if log.exists() else None},
            "database": db["availability"],
            "ledger": ledger_rows(m)["availability"],
            "candles_last_24h": len(candles_24h), "expected_candles_24h": 96,
            "step_failures_24h": sum(1 for e in recent if "step failed" in e["message"]),
            "feed_retries_24h": sum(1 for e in recent if "retry" in e["message"] and e["logger"] == "data"),
            "warnings_24h": sum(1 for e in recent if e["level"] in ("WARNING", "ERROR")),
            "restarts": starts[-10:][::-1],
            "lock_file_present": (ROOT / "state" / m / "bot.lock").exists(),
        }
    return {"modes": out, "observed_utc": iso(now_utc()),
            "not_collected": ["CPU / memory / disk usage", "Docker service health (services run as Windows scheduled tasks)",
                              "exchange connectivity for execution (no live venue connected)"]}


def markets() -> dict:
    cfg = run_cfg("paper")
    hb = {m: heartbeat(m) for m in MODES}
    rows = []
    for base in SYMBOLS:
        sym = bot_symbol(cfg, base)
        c = candles(base, limit=100, source="live")
        closed = [b for b in c["bars"] if b["closed"]]
        last, prev = (closed[-1], closed[-97] if len(closed) > 96 else None) if closed else (None, None)
        rows.append({"symbol": base, "signal_pair": f"{base}/USDT", "signal_venue": "Binance (public market data)",
                     "execution_instrument": sym, "execution_venue": "Delta Exchange India (not connected; paper/shadow only)",
                     "market_profile": cfg.market, "last_close": last["c"] if last else None,
                     "last_closed_utc": c.get("last_closed_utc"), "data_age_min": c.get("data_age_min"),
                     "change_24h_pct": round((last["c"] / prev["c"] - 1) * 100, 2) if last and prev else None,
                     "source": c["source"], "availability": c["availability"],
                     "paper_decision": (hb["paper"].get("last_decisions") or {}).get(base),
                     "shadow_decision": (hb["shadow"].get("last_decisions") or {}).get(base)})
    return {"rows": rows, "observed_utc": iso(now_utc())}


def finite(x):
    return x if not (isinstance(x, float) and not math.isfinite(x)) else None
