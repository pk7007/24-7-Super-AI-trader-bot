import numpy as np
import pandas as pd
import pytest

from bot.config import Settings
from bot.data import validate_candles
from bot.feeds import LiveFeed


@pytest.mark.parametrize("field,value", [("open", float("nan")), ("close", float("inf")),
                                       ("volume", float("nan")), ("volume", float("inf")),
                                       ("open", 105), ("close", 95)])
def test_impossible_or_nonfinite_bars_are_removed(field, value):
    df = pd.DataFrame({"open": [100.], "high": [101.], "low": [99.], "close": [100.], "volume": [1.]},
                      index=pd.date_range("2026-01-01", periods=1, tz="UTC"))
    df.loc[df.index[0], field] = value
    clean, dropped = validate_candles(df)
    assert clean.empty and dropped == 1


def test_daily_risk_feed_refuses_any_corrupted_candle():
    class Exchange:
        def load_markets(self):
            pass

        def fetch_ohlcv(self, *args, **kwargs):
            timestamp = pd.Timestamp("2026-01-01", tz="UTC").value // 1_000_000
            return [[timestamp, 100, 101, 99, np.nan, 1]]

    feed = LiveFeed(Settings(), exchange=Exchange())
    with pytest.raises(ValueError, match="invalid daily"):
        feed.daily_closes("BTC/USD:USD", 10)
