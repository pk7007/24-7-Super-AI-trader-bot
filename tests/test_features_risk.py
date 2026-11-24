import re
from pathlib import Path

import pandas as pd
import pytest

from bot.config import Settings
from bot.features import FEATURE_COLUMNS, build_features, make_labels
from bot.risk import DailyKillSwitch, position_units, stop_price, to_contracts, tp_price
from bot.strategy import decide, should_exit_on_flip
from tests.conftest import make_candles

CFG = Settings()


def test_rule1_features_use_only_closed_candles():
    """Changing candle t and everything after must NOT change the feature row of candle t."""
    df = make_candles(600)
    f1 = build_features(df)
    t = 400
    df2 = df.copy()
    df2.iloc[t:, :4] *= 1.37
    df2.iloc[t:, 4] *= 5
    f2 = build_features(df2)
    pd.testing.assert_frame_equal(f1.iloc[: t + 1], f2.iloc[: t + 1])
    assert not f1.iloc[t + 1].equals(f2.iloc[t + 1])  # sanity: candle t does feed row t+1


def test_features_columns_and_first_row_empty():
    f = build_features(make_candles(300))
    assert list(f.columns) == FEATURE_COLUMNS
    assert f.iloc[0].isna().all()  # shift(1): nothing is known before the first close


def test_labels_unresolved_tail_is_nan():
    df = make_candles(300)
    f = build_features(df)
    y = make_labels(df, f, horizon=16, k=CFG.label_k)
    assert y.iloc[-15:].isna().all()
    assert set(y.dropna().unique()) <= {0.0, 1.0, 2.0}


def test_position_size_risks_exactly_risk_per_trade():
    equity, price, atr = 1000.0, 60000.0, 0.004
    units = position_units(equity, price, atr, CFG)
    loss_at_stop = units * price * CFG.stop_atr * atr
    assert loss_at_stop == pytest.approx(equity * CFG.risk_per_trade)


def test_leverage_cap_and_bad_inputs():
    units = position_units(1000.0, 100.0, 0.0001, CFG)  # tiny ATR -> huge raw size
    assert units * 100.0 <= 1000.0 * CFG.max_leverage + 1e-9
    assert position_units(1000.0, 100.0, 0.0, CFG) == 0
    assert position_units(1000.0, 100.0, float("nan"), CFG) == 0
    assert position_units(0.0, 100.0, 0.01, CFG) == 0


def test_contracts_round_down_never_up():
    assert to_contracts(0.0259, 0.001) == 25
    assert to_contracts(0.0004, 0.001) == 0


def test_stop_and_tp_geometry():
    assert stop_price(1, 100, 0.01, CFG) < 100 < tp_price(1, 100, 0.01, CFG)
    assert tp_price(-1, 100, 0.01, CFG) < 100 < stop_price(-1, 100, 0.01, CFG)


def test_rule4_killswitch_threshold():
    ks = DailyKillSwitch(0.03)
    ks.roll("2026-01-01", 1000.0)
    assert not ks.check(971.0)  # -2.9%
    assert ks.check(970.0)  # -3.0% trips, once
    assert not ks.check(900.0)
    assert ks.halted
    assert ks.roll("2026-01-02", 970.0) and not ks.halted  # new UTC day re-arms and re-bases


def test_decide_thresholds_and_nan():
    assert decide(0.1, 0.8, CFG) == 1
    assert decide(0.8, 0.1, CFG) == -1
    assert decide(0.4, 0.45, CFG) == 0  # margin too small
    assert decide(float("nan"), 0.9, CFG) == 0
    assert should_exit_on_flip(1, 0.8, 0.1, CFG) and not should_exit_on_flip(1, 0.1, 0.8, CFG)


def test_spot_mode_blocks_shorts_but_still_exits_longs_on_bearish_flip():
    from dataclasses import replace

    spot = replace(CFG, allow_short=False, max_leverage=1.0)
    assert decide(0.8, 0.1, spot) == 0 and decide(0.8, 0.1, CFG) == -1  # no short entry on spot
    assert decide(0.1, 0.8, spot) == 1
    assert should_exit_on_flip(1, 0.8, 0.1, spot)  # a long still exits when the model turns bearish


def test_from_env_defaults_to_spot_long_only_no_leverage(monkeypatch):
    for k in ("MARKET", "STRATEGY"):
        monkeypatch.delenv(k, raising=False)
    s = Settings.from_env()
    assert s.market == "spot" and not s.allow_short and s.max_leverage == 1.0 and s.funding_per_8h == 0.0
    monkeypatch.setenv("MARKET", "perp")
    assert Settings.from_env().allow_short  # opt-in only


def test_spot_feed_uses_fractional_steps_perp_uses_contracts():
    from dataclasses import replace

    from bot.feeds import DEFAULT_CONTRACT_SIZE, LiveFeed, SPOT_STEP

    class Dummy:
        def load_markets(self):
            pass

    spot = LiveFeed(replace(CFG, market="spot"), exchange=Dummy())
    perp = LiveFeed(replace(CFG, market="perp"), exchange=Dummy())
    assert spot.contract_size("SOL/USD:USD") == SPOT_STEP["SOL/USD:USD"] == 0.01
    assert perp.contract_size("SOL/USD:USD") == DEFAULT_CONTRACT_SIZE["SOL/USD:USD"] == 1.0


def test_rule6_no_hardcoded_secrets():
    pat = re.compile(r"""(api[_-]?key|secret|token|password)\s*[:=]\s*["'][A-Za-z0-9_\-]{12,}["']""", re.I)
    for p in Path(__file__).resolve().parent.parent.joinpath("bot").rglob("*.py"):
        assert not pat.search(p.read_text(encoding="utf-8")), f"possible secret in {p}"


def test_rule6_live_requires_explicit_consent(monkeypatch):
    from bot.broker.delta import DeltaBroker, LiveTradingNotAllowed, require_live_consent

    monkeypatch.setenv("BOT_MODE", "paper")
    monkeypatch.delenv("I_UNDERSTAND_LIVE_RISK", raising=False)
    with pytest.raises(LiveTradingNotAllowed):
        require_live_consent()
    monkeypatch.setenv("BOT_MODE", "live")
    with pytest.raises(LiveTradingNotAllowed):
        require_live_consent()  # still missing the explicit acknowledgement
    monkeypatch.setenv("I_UNDERSTAND_LIVE_RISK", "yes")
    require_live_consent()
    monkeypatch.delenv("DELTA_API_KEY", raising=False)
    monkeypatch.delenv("DELTA_API_SECRET", raising=False)
    with pytest.raises(LiveTradingNotAllowed):
        DeltaBroker(Settings())  # no keys in the environment -> refuses
