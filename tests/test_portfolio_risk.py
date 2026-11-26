"""Portfolio risk: 1-day historical Expected Shortfall cap (correlation-aware) and a gross exposure cap."""

import logging
from dataclasses import replace

import numpy as np
import pandas as pd
import pytest

from bot.config import Settings, enforce_policy
from bot.feeds import ReplayFeed
from bot.portfolio_risk import MIN_DAYS, check_entry, daily_returns, es_var

SYM = "BTC/USD:USD"
DAYS = pd.date_range("2026-01-01", periods=120, freq="1D", tz="UTC")


def closes(vol, seed=0, n=120):
    r = np.random.default_rng(seed).normal(0, vol, n)
    return pd.Series(100 * np.exp(np.cumsum(r)), index=DAYS[:n])


def fn(series_by_sym):
    return lambda sym, days: series_by_sym[sym]


CFG = Settings(mode="paper", start_equity=1000.0, symbols=(SYM, "ETH/USD:USD"), max_leverage=1.0)


def test_es_is_the_mean_of_the_worst_tail_and_at_least_var():
    rets = pd.DataFrame({"A": np.r_[np.full(36, 0.01), -0.05, -0.10, -0.20, -0.40]})
    var99, es = es_var({"A": 100.0}, rets, alpha=0.95)
    assert es == pytest.approx(30.0)           # worst 2 of 40 days: (20 + 40) / 2
    assert var99 > 0
    assert es >= float((-rets["A"] * 100).quantile(0.95))  # ES at a level is never below VaR at that level


def test_correlated_coins_add_up_independent_coins_diversify():
    a = closes(0.04, seed=1).pct_change().dropna()
    same = pd.DataFrame({"A": a, "B": a})                       # correlation 1
    indep = pd.DataFrame({"A": a, "B": closes(0.04, seed=2).pct_change().dropna()})
    one = es_var({"A": 100.0}, same)[1]
    assert es_var({"A": 100.0, "B": 100.0}, same)[1] == pytest.approx(2 * one)
    assert es_var({"A": 100.0, "B": 100.0}, indep)[1] < 2 * one  # correlation is what the joint ES captures


def test_small_position_passes_and_reports_es_and_correlation():
    v = check_entry({"ETH/USD:USD": 45.0}, SYM, 45.0, 1000.0, fn({SYM: closes(0.04, 1), "ETH/USD:USD": closes(0.05, 2)}), CFG)
    assert v.ok, v.reason
    assert 0 < v.es < 0.02 * 1000 and "ETH/USD:USD" in v.corr


def test_entry_refused_when_portfolio_es_exceeds_cap():
    v = check_entry({}, SYM, 600.0, 1000.0, fn({SYM: closes(0.08, 3)}), CFG)
    assert not v.ok and "expected shortfall" in v.reason


def test_entry_refused_when_gross_exposure_exceeds_leverage_cap():
    v = check_entry({"ETH/USD:USD": 700.0}, SYM, 400.0, 1000.0, fn({}), CFG)
    assert not v.ok and "gross exposure" in v.reason


def test_history_failure_refuses_entry():
    def boom(sym, days):
        raise ConnectionError("down")
    v = check_entry({}, SYM, 45.0, 1000.0, boom, CFG)
    assert not v.ok and "history unavailable" in v.reason


def test_short_history_refuses_live_but_only_warns_in_replay():
    short = fn({SYM: closes(0.04, n=MIN_DAYS - 5)})
    assert not check_entry({}, SYM, 45.0, 1000.0, short, CFG).ok
    v = check_entry({}, SYM, 45.0, 1000.0, short, replace(CFG, mode="replay"))
    assert v.ok and "skipped" in v.reason


def test_policy_refuses_a_looser_es_cap():
    with pytest.raises(ValueError, match="max_es_pct"):
        enforce_policy(replace(CFG, max_es_pct=0.05))
    enforce_policy(replace(CFG, max_es_pct=0.01))  # stricter is allowed


def test_replay_daily_closes_never_include_the_forming_day():
    idx = pd.date_range("2026-01-01", periods=96 * 5, freq="15min", tz="UTC")
    df = pd.DataFrame({c: np.arange(len(idx), dtype=float) + 1 for c in ("open", "high", "low", "close", "volume")}, index=idx)
    feed = ReplayFeed({SYM: df}, CFG)
    feed.set_time(pd.Timestamp("2026-01-04 06:00", tz="UTC"))   # day 4 is still forming
    d = feed.daily_closes(SYM, 30)
    assert list(d.index.strftime("%m-%d")) == ["01-01", "01-02", "01-03"]
    assert d.iloc[-1] == df.loc["2026-01-03 23:45", "close"]       # last CLOSED 15m candle of day 3


def test_engine_skips_entry_on_es_breach_and_logs_why(world, caplog, monkeypatch):
    eng = world["make_engine"]()
    eng.reconcile()
    monkeypatch.setattr(world["feed"], "daily_closes", lambda s, d: closes(0.6, 5), raising=False)
    caplog.set_level(logging.INFO, logger="engine")
    eng.step(world["feed"].now())
    assert not world["broker"].positions()
    assert any("portfolio risk" in r.getMessage() for r in caplog.records)


def test_engine_enters_when_es_is_within_cap(world, monkeypatch):
    eng = world["make_engine"]()
    eng.reconcile()
    monkeypatch.setattr(world["feed"], "daily_closes", lambda s, d: closes(0.005, 6), raising=False)
    eng.step(world["feed"].now())
    assert SYM in world["broker"].positions()


def test_daily_returns_align_dates():
    r = daily_returns({"A": closes(0.01, 1), "B": closes(0.01, 2).iloc[10:]})
    assert len(r) == 109 and list(r.columns) == ["A", "B"]
