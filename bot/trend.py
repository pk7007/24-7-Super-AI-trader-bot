"""Rule-based time-series trend strategy (default). Same interface as the ML signal.

Long when price > EMA(span) and the EMA is rising over the last day; short when the opposite;
otherwise no signal. The position is held until the opposite signal appears or the exchange-side
stop (``stop_atr`` x daily-scale ATR) is hit. Every output column is shifted by one candle (RULE 1).

Honest status: in a 444-day walk-forward window (a bear market) the 14-day variant returned
about +20% with a ~10% drawdown, but ALL of it came from the second half; the first half was flat.
Treat it as a weak, regime-dependent edge, not a proven one.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from .features import atr


class TrendModel:
    def __init__(self, span_days: int = 14, bars_per_day: int = 96):
        self.bpd = bars_per_day
        self.span = span_days * bars_per_day
        self.min_candles = max(3 * self.span, 288)  # EMA warm-up
        self.lookback = self.min_candles + bars_per_day * 3

    def frame(self, df: pd.DataFrame) -> pd.DataFrame:
        """Columns p_down, p_flat, p_up, atr_pct for every row, known at that candle's OPEN."""
        c = df["close"]
        ema = c.ewm(span=self.span, adjust=False).mean()
        slope = ema - ema.shift(self.bpd)
        long_, short_ = (c > ema) & (slope > 0), (c < ema) & (slope < 0)
        out = pd.DataFrame(0.05, index=df.index, columns=["p_down", "p_flat", "p_up"])
        out.loc[long_, "p_up"] = 0.9
        out.loc[short_, "p_down"] = 0.9
        out["atr_pct"] = atr(df, self.bpd * 14) / c * np.sqrt(self.bpd)  # ~daily-scale ATR
        return out.shift(1)

    def predict_from_candles(self, ext: pd.DataFrame):
        """``ext`` = closed candles + one placeholder row for the candle that is opening now."""
        if len(ext) < self.min_candles:
            return None
        row = self.frame(ext).iloc[-1]
        return row[["p_down", "p_flat", "p_up"]], float(row["atr_pct"])
