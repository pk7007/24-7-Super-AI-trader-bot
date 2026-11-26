"""CLI:  python -m bot.main <command>

  fetch      download/refresh candle history from Delta Exchange India (public API)
  backtest   walk-forward, out-of-sample backtest with realistic costs
  train      fit the production model on the latest data -> models/model.joblib
  replay     run the FULL engine (paper broker, stops, kill-switch, ledger) over recent history
  paper      24/7 paper trading on live market data (no real orders)
  live       real orders on Delta Exchange (needs BOT_MODE=live + consent + keys)
  report     summarise the ledger of a mode
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import shutil
import sys
from dataclasses import replace

import pandas as pd

from . import heartbeat, notify
from .backtest import prepare, simulate, walk_forward_probs
from .broker.paper import PaperBroker
from .config import ROOT, Settings, load_env
from .data import load_or_fetch, read_cached
from .engine import Engine
from .feeds import LiveFeed, ReplayFeed
from .ledger import Ledger
from .model import SignalModel
from .report import summarise
from .state import State
from .trend import TrendModel

log = logging.getLogger("main")


_LOCKS: list = []  # keep lock handles open for the life of the process


def single_instance(cfg: Settings):
    """Refuse to start a second bot for the same mode/run dir (prevents two processes trading one account)."""
    import os

    path = cfg.run_dir / "bot.lock"
    path.parent.mkdir(parents=True, exist_ok=True)
    fh = open(path, "a+")
    try:
        if os.name == "nt":
            import msvcrt

            fh.seek(0)
            msvcrt.locking(fh.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl

            fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        fh.close()
        raise SystemExit(f"another {cfg.mode} bot is already running (lock {path}); refusing to start")
    _LOCKS.append(fh)
    return fh


def setup_logging(mode: str) -> None:
    (ROOT / "state").mkdir(exist_ok=True)
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=[logging.StreamHandler(sys.stdout), logging.FileHandler(ROOT / "state" / f"{mode}.log")],
    )


def load_data(cfg: Settings) -> dict[str, pd.DataFrame]:
    return {s: read_cached(cfg, s) for s in cfg.symbols}


def get_model(cfg: Settings):
    """Trend rules by default; the LightGBM model only when STRATEGY=ml and a model file exists."""
    if cfg.strategy == "trend":
        return TrendModel(cfg.trend_span_days)
    if cfg.strategy == "ensemble":
        from .lab import EnsembleModel

        return EnsembleModel(cfg.trend_span_days)
    return SignalModel.load(cfg.model_path)


def train_model(cfg: Settings, data, end: pd.Timestamp, days: int) -> SignalModel:
    feats, labels = prepare(cfg, data)
    tf = pd.Timedelta(minutes=cfg.tf_minutes)
    cut, lo = end - cfg.horizon * tf, end - pd.Timedelta(days=days)
    X = pd.concat([feats[s][(feats[s].index >= lo) & (feats[s].index < cut)] for s in data])
    y = pd.concat([labels[s][(labels[s].index >= lo) & (labels[s].index < cut)] for s in data])
    return SignalModel().fit(X, y)


# --------------------------------------------------------------------------- commands
def cmd_fetch(cfg: Settings, a) -> None:
    for s in cfg.symbols:
        df = load_or_fetch(cfg, s, a.days, refresh=a.refresh)
        print(f"{s}: {len(df)} candles {df.index[0]} -> {df.index[-1]}")


def cmd_backtest(cfg: Settings, a) -> None:
    data = load_data(cfg)
    first = max(d.index[0] for d in data.values())
    last = min(d.index[-1] for d in data.values()) + pd.Timedelta(minutes=cfg.tf_minutes)
    start = first + pd.Timedelta(days=cfg.train_days + 5)
    if cfg.strategy in ("trend", "ensemble"):
        tm = get_model(cfg)
        frames = {s: tm.frame(d) for s, d in data.items()}
        feats = {s: f[["atr_pct"]] for s, f in frames.items()}
        probs = {s: f[["p_down", "p_flat", "p_up"]] for s, f in frames.items()}
    else:
        feats, labels = prepare(cfg, data)
        probs = walk_forward_probs(cfg, data, feats, labels, start, last)
    res = simulate(cfg, data, feats, probs, start, last)
    out = ROOT / "reports"
    out.mkdir(exist_ok=True)
    res.curve.to_csv(out / "backtest_equity.csv")
    pd.DataFrame([t.__dict__ for t in res.trades]).to_csv(out / "backtest_trades.csv", index=False)
    bh = {s: round((d.loc[start:last, "close"].iloc[-1] / d.loc[start:last, "close"].iloc[0] - 1) * 100, 1)
          for s, d in data.items()}
    res.metrics["buy_and_hold_pct"] = bh
    (out / "backtest_metrics.json").write_text(json.dumps(res.metrics, indent=2, default=str))
    print(json.dumps(res.metrics, indent=2, default=str))


def cmd_train(cfg: Settings, a) -> None:
    data = load_data(cfg)
    end = min(d.index[-1] for d in data.values()) + pd.Timedelta(minutes=cfg.tf_minutes)
    m = train_model(cfg, data, end, a.days)
    m.save(cfg.model_path)
    print(f"model saved -> {cfg.model_path}")


def delta_venue_price(cfg: Settings):
    """Execution-venue (Delta India) last price, used as a sanity guard before entries."""
    from .data import make_public_exchange

    ex = make_public_exchange(cfg)
    return lambda sym: float(ex.fetch_ticker(sym)["last"])


def build_engine(cfg: Settings, feed, broker, model, venue_price=None) -> Engine:
    state = State(cfg.db_path)
    return Engine(cfg, broker, feed, model, state, Ledger(cfg.ledger_csv, state), notify=notify.send,
                  venue_price=venue_price)


def cmd_replay(cfg: Settings, a) -> None:
    """Full-engine replay over the most recent ``days`` using a model trained BEFORE that window."""
    cfg = replace(cfg, mode="replay")
    if cfg.run_dir.exists():
        shutil.rmtree(cfg.run_dir)
    data = load_data(cfg)
    last = min(d.index[-1] for d in data.values()) + pd.Timedelta(minutes=cfg.tf_minutes)
    start = last - pd.Timedelta(days=a.days)
    model = get_model(cfg) if cfg.strategy in ("trend", "ensemble") else train_model(cfg, data, start, cfg.train_days)
    feed = ReplayFeed(data, cfg)
    feed.set_time(start)
    broker = PaperBroker(feed, cfg, cfg.paper_exchange_path)
    eng = build_engine(cfg, feed, broker, model)
    eng.reconcile()
    idx = sorted(set().union(*[set(d.index[(d.index >= start) & (d.index < last)]) for d in data.values()]))
    for ts in idx:
        feed.set_time(ts)
        eng.monitor(ts)
        eng.step(ts)
    feed.set_time(last)
    eng.monitor(last)
    summary = summarise(eng.state.fills(), cfg, broker.equity())
    summary.update(window=f"{start} -> {last}", start_equity_usd=cfg.start_equity,
                   open_positions=list(broker.positions()))
    (ROOT / "reports").mkdir(exist_ok=True)
    (ROOT / "reports" / "replay_summary.json").write_text(json.dumps(summary, indent=2, default=str))
    print(json.dumps(summary, indent=2, default=str))


def _utcnow() -> pd.Timestamp:
    return pd.Timestamp.now(tz="UTC")


STEP_RETRY_DELAYS = (30, 60, 120, 240)  # seconds; a failed candle is retried, never skipped on the first error


async def step_with_retry(eng, ts: pd.Timestamp, deadline: pd.Timestamp, delays=STEP_RETRY_DELAYS,
                          now=_utcnow, sleep=asyncio.sleep, notify=notify.send) -> bool:
    """Run ``eng.step(ts)``; on failure retry the SAME candle after each delay, stopping before ``deadline``.

    Safe to repeat: step skips coins already held and re-checks every limit, so a retry cannot double-enter.
    Alerts once, only if every attempt failed. Returns True if the candle was processed.
    """
    attempt, exc = 0, None
    while True:
        try:
            await asyncio.to_thread(eng.step, ts)
            if attempt:
                log.info("step for candle %s recovered on retry %d", ts.strftime("%m-%d %H:%M"), attempt)
            return True
        except Exception as e:  # noqa: BLE001 - any failure is retried, then reported
            exc = e
            # Not "step failed ...": alerts and the dashboard count those lines as lost candles.
            log.warning("step attempt %d failed: %s: %s", attempt + 1, type(e).__name__, e, exc_info=True)
        if attempt >= len(delays) or now() + pd.Timedelta(seconds=delays[attempt]) > deadline:
            break
        await sleep(delays[attempt])
        attempt += 1
    msg = (f"step failed after {attempt + 1} attempts, candle {ts.strftime('%m-%d %H:%M')} skipped: "
           f"{type(exc).__name__}: {exc}")
    log.error(msg)
    notify(msg)
    return False


async def run_forever(eng: Engine, cfg: Settings) -> None:
    from .keepawake import prevent_sleep

    tf = pd.Timedelta(minutes=cfg.tf_minutes)
    prevent_sleep()  # most missed candles were the PC idle-sleeping; KEEP_AWAKE=0 turns this off
    await asyncio.to_thread(eng.reconcile)  # RULE 3: before anything else
    log.info("reconciled; entering main loop (%s)", cfg.mode)
    # No-op unless HEARTBEAT_URL is set. Pings every 5 min (also during retries); stops after a skipped candle.
    pacer = heartbeat.Pacer(cfg.run_dir / "heartbeat.json")

    async def wait(seconds: float) -> None:
        """Sleep in short slices, evaluating resting stops and the kill-switch between them."""
        end = _utcnow() + pd.Timedelta(seconds=seconds)
        while (rem := (end - _utcnow()).total_seconds()) > 0:
            await asyncio.sleep(min(20, rem))
            try:
                await asyncio.to_thread(eng.monitor, _utcnow())
            except Exception:
                log.exception("monitor failed")
            try:
                await asyncio.to_thread(pacer.tick)
            except Exception:  # monitoring must never stop trading
                log.exception("heartbeat tick failed")

    while True:
        now = _utcnow()
        nxt = now.ceil(f"{cfg.tf_minutes}min")
        if nxt <= now:
            nxt += tf
        await wait((nxt - _utcnow()).total_seconds())
        await asyncio.sleep(4)  # let the exchange publish the closed candle
        ok = await step_with_retry(eng, nxt, deadline=nxt + tf - pd.Timedelta(seconds=60), sleep=wait)
        try:
            await asyncio.to_thread(pacer.candle, ok)
        except Exception:
            log.exception("heartbeat ping failed")


def cmd_paper(cfg: Settings, a) -> None:
    cfg = replace(cfg, mode="paper")
    single_instance(cfg)
    setup_logging("paper")
    model = get_model(cfg)
    feed = LiveFeed(cfg)
    broker = PaperBroker(feed, cfg, cfg.paper_exchange_path)
    # The Delta price guard only makes sense when the execution venue IS Delta (perp mode).
    venue = delta_venue_price(cfg) if cfg.market == "perp" else None
    asyncio.run(run_forever(build_engine(cfg, feed, broker, model, venue), cfg))


def cmd_shadow(cfg: Settings, a) -> None:
    """Shadow trading: live public data, production risk checks, order intentions logged, no real orders."""
    from .broker.shadow import ShadowBroker

    cfg = replace(cfg, mode="shadow")
    single_instance(cfg)
    setup_logging("shadow")
    model = get_model(cfg)
    feed = LiveFeed(cfg)
    broker = ShadowBroker(feed, cfg, cfg.paper_exchange_path, cfg.run_dir / "shadow_intents.csv")
    asyncio.run(run_forever(build_engine(cfg, feed, broker, model, None), cfg))


def cmd_live(cfg: Settings, a) -> None:
    from .broker.delta import DeltaBroker, require_live_consent

    require_live_consent()
    cfg = replace(cfg, mode="live")
    single_instance(cfg)
    setup_logging("live")
    model = get_model(cfg)
    feed = LiveFeed(cfg)
    asyncio.run(run_forever(build_engine(cfg, feed, DeltaBroker(cfg), model, delta_venue_price(cfg)), cfg))


def cmd_lab(cfg: Settings, a) -> None:
    from .lab import run_lab

    c = replace(cfg, strategy="trend")
    if a.taker is not None:  # fee stress test
        c = replace(c, taker_fee=a.taker, maker_fee=a.taker)
    run_lab(c, load_data(cfg), only=a.only.split(",") if a.only else None, tag=a.tag)


def cmd_feasibility(cfg: Settings, a) -> None:
    from .feasibility import run

    print(run(cfg))


def cmd_testnet_check(cfg: Settings, a) -> None:
    from .testnet_check import run

    sys.exit(0 if run(cfg, asset=a.asset) else 1)


def cmd_report(cfg: Settings, a) -> None:
    cfg = replace(cfg, mode=a.mode)
    state = State(cfg.db_path)
    print(json.dumps(summarise(state.fills(), cfg), indent=2))


def main(argv: list[str] | None = None) -> None:
    load_env()
    cfg = Settings.from_env()
    p = argparse.ArgumentParser(prog="bot")
    sub = p.add_subparsers(dest="cmd", required=True)
    f = sub.add_parser("fetch"); f.add_argument("--days", type=int, default=540); f.add_argument("--refresh", action="store_true")
    sub.add_parser("backtest")
    t = sub.add_parser("train"); t.add_argument("--days", type=int, default=180)
    r = sub.add_parser("replay"); r.add_argument("--days", type=int, default=45)
    sub.add_parser("paper"); sub.add_parser("live"); sub.add_parser("shadow")
    rp = sub.add_parser("report"); rp.add_argument("--mode", default="paper")
    sub.add_parser("feasibility")
    lb = sub.add_parser("lab")
    lb.add_argument("--only", default="", help="comma list of candidates")
    lb.add_argument("--taker", type=float, default=None, help="override taker=maker fee, e.g. 0.0025")
    lb.add_argument("--tag", default="lab")
    tc = sub.add_parser("testnet-check"); tc.add_argument("--asset", default="USD", help="balance asset name")
    a = p.parse_args(argv)
    if a.cmd not in ("paper", "live", "shadow"):
        logging.basicConfig(level=logging.WARNING)
    {"fetch": cmd_fetch, "backtest": cmd_backtest, "train": cmd_train, "replay": cmd_replay,
     "paper": cmd_paper, "live": cmd_live, "shadow": cmd_shadow, "report": cmd_report,
     "testnet-check": cmd_testnet_check, "lab": cmd_lab,
     "feasibility": cmd_feasibility}[a.cmd](cfg, a)


if __name__ == "__main__":
    main()
