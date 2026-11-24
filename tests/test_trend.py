import pandas as pd

from bot.trend import TrendModel
from tests.conftest import SYM, make_candles


def test_rule1_trend_signal_ignores_current_and_future_candles():
    df = make_candles(1500, drift=0.0004)
    tm = TrendModel(span_days=1)
    f1 = tm.frame(df)
    t = 1000
    df2 = df.copy()
    df2.iloc[t:, :4] *= 0.5
    f2 = tm.frame(df2)
    pd.testing.assert_frame_equal(f1.iloc[: t + 1], f2.iloc[: t + 1])


def test_trend_direction_follows_drift():
    up, down = make_candles(1500, drift=0.0008, vol=0.0005), make_candles(1500, drift=-0.0008, vol=0.0005)
    tm = TrendModel(span_days=1)
    assert tm.frame(up).iloc[-1]["p_up"] > 0.5
    assert tm.frame(down).iloc[-1]["p_down"] > 0.5


def test_trend_needs_warmup():
    assert TrendModel(14).predict_from_candles(make_candles(500)) is None


def test_engine_trades_with_trend_model_and_attaches_stop(world):
    world["data"][SYM] = make_candles(1500, drift=0.0008, vol=0.0005)  # clean uptrend
    world["feed"].data = world["data"]
    world["feed"].set_time(world["data"][SYM].index[1200])
    eng = world["make_engine"](TrendModel(span_days=1))
    eng.reconcile()
    eng.step(world["feed"].now())
    pos = world["state"].positions()[SYM]
    assert pos.side == 1 and pos.stop_id in world["broker"].open_stop_ids(SYM) and pos.stop < pos.entry
