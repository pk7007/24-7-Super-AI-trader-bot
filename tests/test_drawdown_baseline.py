import pandas as pd
from bot.backtest import Result, metrics
from bot.config import Settings


def test_first_bar_loss_counts_toward_backtest_drawdown():
    cfg = Settings(start_equity=100)
    result = Result(curve=pd.Series([90., 95.], index=pd.date_range("2026-01-01", periods=2, tz="UTC")))
    assert metrics(cfg, result)["max_drawdown_pct"] == -10
