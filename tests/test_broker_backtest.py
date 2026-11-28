import json

import numpy as np
import pandas as pd
import pytest

from bot.backtest import simulate
from bot.config import Settings
from bot.report import round_trips, summarise
from tests.conftest import SYM


def test_paper_broker_accounting(world):
    b, feed, cfg = world["broker"], world["feed"], world["cfg"]
    d = world["data"][SYM]
    p0 = feed.last_price(SYM)
    buy = b.market_order(SYM, "buy", 10, reason="entry")
    assert buy.price == pytest.approx(p0 * (1 + cfg.slippage))
    assert buy.fee == pytest.approx(10 * 0.001 * buy.price * cfg.taker_fee * cfg.gst)
    feed.set_time(d.index[410])
    p1 = feed.last_price(SYM)
    sell = b.market_order(SYM, "sell", 10, reduce_only=True, reason="x")
    expected = (sell.price - buy.price) * 10 * 0.001
    assert sell.realized_pnl == pytest.approx(expected)
    assert b.s["cash"] == pytest.approx(cfg.start_equity + expected - buy.fee - sell.fee)
    assert not b.positions()
    assert b.market_order(SYM, "sell", 5, reduce_only=True) is None  # nothing left to reduce


def test_paper_reduce_only_cannot_flip(world):
    b = world["broker"]
    b.market_order(SYM, "buy", 10)
    b.market_order(SYM, "sell", 50, reduce_only=True)
    assert not b.positions()  # capped at 10, did not open a short


def test_paper_state_survives_restart(world):
    from bot.broker.paper import PaperBroker

    b = world["broker"]
    b.market_order(SYM, "buy", 7)
    sid = b.place_stop(SYM, "sell", 7, 1.0)
    b2 = PaperBroker(world["feed"], world["cfg"], world["tmp"] / "ex.json")
    assert b2.positions()[SYM].contracts == 7 and sid in b2.open_stop_ids(SYM)


def test_paper_save_reaches_the_disk_before_it_replaces_the_account(world, monkeypatch):
    """A power cut on 2026-11-27 left ex.json as zero bytes: the rename was on disk, the data was not."""
    import os

    events = []
    real_fsync, real_replace = os.fsync, os.replace
    monkeypatch.setattr(os, "fsync", lambda fd: (events.append("fsync"), real_fsync(fd))[1])
    monkeypatch.setattr(os, "replace", lambda a, b: (events.append("replace"), real_replace(a, b))[1])
    world["broker"].market_order(SYM, "buy", 3)
    assert "replace" in events and events.index("fsync") < events.index("replace")
    assert json.loads((world["tmp"] / "ex.json").read_text())["positions"]


def _flat_world(n=60):
    idx = pd.date_range("2026-01-01", periods=n, freq="15min", tz="UTC", name="date")
    px = np.full(n, 100.0)
    df = pd.DataFrame({"open": px, "high": px * 1.001, "low": px * 0.999, "close": px,
                       "volume": 1.0}, index=idx)
    feats = {SYM: pd.DataFrame({"atr_pct": 0.002}, index=idx)}
    probs = {SYM: pd.DataFrame(np.nan, index=idx, columns=["p_down", "p_flat", "p_up"])}
    return df, feats, probs, idx


def test_backtest_flat_market_loses_exactly_costs():
    cfg = Settings()
    df, feats, probs, idx = _flat_world()
    probs[SYM].loc[idx[20]] = [0.05, 0.05, 0.9]
    res = simulate(cfg, {SYM: df}, feats, probs, idx[0], idx[-1] + pd.Timedelta(minutes=15))
    assert len(res.trades) == 1
    t = res.trades[0]
    assert t.reason == "time" and t.pnl < 0
    assert abs(t.pnl) < 0.01 * cfg.start_equity  # costs only, a few bps of notional
    assert t.fees > 0
    assert res.metrics["end_equity"] < cfg.start_equity


def test_backtest_stop_beats_tp_when_both_touched_in_one_candle():
    cfg = Settings()
    df, feats, probs, idx = _flat_world()
    df.loc[idx[21], ["high", "low"]] = [102.0, 98.0]  # spans both the TP and the stop
    probs[SYM].loc[idx[20]] = [0.05, 0.05, 0.9]
    res = simulate(cfg, {SYM: df}, feats, probs, idx[0], idx[-1] + pd.Timedelta(minutes=15))
    assert res.trades[0].reason == "stop" and res.trades[0].pnl < 0


def test_backtest_kill_switch_stops_trading_for_the_day():
    cfg = Settings(risk_per_trade=0.05, max_leverage=20.0)  # oversized on purpose
    df, feats, probs, idx = _flat_world(n=90)
    df.loc[idx[21]:, ["open", "high", "low", "close"]] *= 0.97  # -3% gap, same UTC day
    probs[SYM].loc[idx[20]] = [0.05, 0.05, 0.9]
    probs[SYM].loc[idx[30]] = [0.05, 0.05, 0.9]  # would re-enter later the same day
    res = simulate(cfg, {SYM: df}, feats, probs, idx[0], idx[-1] + pd.Timedelta(minutes=15))
    assert len(res.trades) == 1  # second signal blocked by the kill-switch


def test_report_round_trips_and_tax():
    fills = [
        dict(ts="1", symbol="A", side="buy", qty=10, price=100, fee=1.0, realized_pnl=0.0, reason="entry"),
        dict(ts="2", symbol="A", side="sell", qty=10, price=110, fee=1.0, realized_pnl=50.0, reason="tp"),
        dict(ts="3", symbol="A", side="buy", qty=10, price=100, fee=1.0, realized_pnl=0.0, reason="entry"),
        dict(ts="4", symbol="A", side="sell", qty=10, price=95, fee=1.0, realized_pnl=-30.0, reason="stop"),
    ]
    trips = round_trips(fills)
    assert [round(t["net"], 2) for t in trips] == [48.0, -32.0]
    s = summarise(fills, Settings(usdt_inr=100.0))
    assert s["net_pnl_usd"] == 16.0 and s["win_rate_pct"] == 50.0
    assert s["est_tax_30pct_inr"] == round(48.0 * 100 * 0.30)  # losses do NOT offset gains


def test_shadow_broker_logs_intents_and_refuses_other_modes(tmp_path):
    import csv
    from dataclasses import replace

    from bot.broker.shadow import ShadowBroker
    from bot.config import Settings
    from bot.feeds import ReplayFeed
    from tests.conftest import SYM, make_candles

    cfg = Settings(mode="shadow", start_equity=1000.0, symbols=(SYM,))
    data = {SYM: make_candles()}
    feed = ReplayFeed(data, cfg)
    feed.set_time(data[SYM].index[400])
    b = ShadowBroker(feed, cfg, tmp_path / "ex.json", tmp_path / "intents.csv")
    fill = b.market_order(SYM, "buy", 1, reason="entry")
    b.place_stop(SYM, "sell", 1, fill.price * 0.95)
    rows = list(csv.DictReader((tmp_path / "intents.csv").open()))
    assert [r["reason"] for r in rows][0] == "entry" and rows[1]["reason"].startswith("stop@")
    assert float(rows[0]["modeled_slippage_pct"]) > 0
    with pytest.raises(RuntimeError):
        ShadowBroker(feed, replace(cfg, mode="live"), tmp_path / "x.json", tmp_path / "i.csv")
