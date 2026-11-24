"""Feature engineering. RULE 1: every feature is shifted by one candle.

Row ``t`` of the returned frame describes the market as of the CLOSE of candle ``t-1``.
That is exactly what is knowable when candle ``t`` opens, so a model scored on row ``t``
can place an order at the open of candle ``t`` without look-ahead.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

FEATURE_COLUMNS = [
    "ret_1", "ret_4", "ret_16", "ret_64",
    "atr_pct", "atr_ratio", "rsi",
    "ema_dist_20", "ema_dist_50", "ema_dist_200",
    "bb_pos", "bb_width", "vol_z", "range_pct",
    "hour_sin", "hour_cos", "dow",
]


def _rsi(close: pd.Series, n: int = 14) -> pd.Series:
    d = close.diff()
    up = d.clip(lower=0).ewm(alpha=1 / n, adjust=False).mean()
    dn = (-d.clip(upper=0)).ewm(alpha=1 / n, adjust=False).mean()
    return 100 - 100 / (1 + up / dn.replace(0, np.nan))


def atr(df: pd.DataFrame, n: int = 14) -> pd.Series:
    pc = df["close"].shift()
    tr = pd.concat(
        [df["high"] - df["low"], (df["high"] - pc).abs(), (df["low"] - pc).abs()], axis=1
    ).max(axis=1)
    return tr.ewm(alpha=1 / n, adjust=False).mean()


def raw_features(df: pd.DataFrame) -> pd.DataFrame:
    """Unshifted features computed on candle t using data up to and including t."""
    c, v = df["close"], df["volume"]
    f = pd.DataFrame(index=df.index)
    for n in (1, 4, 16, 64):
        f[f"ret_{n}"] = c.pct_change(n)
    f["atr_pct"] = atr(df) / c
    f["atr_ratio"] = f["atr_pct"] / f["atr_pct"].rolling(96).mean()
    f["rsi"] = _rsi(c)
    for n in (20, 50, 200):
        f[f"ema_dist_{n}"] = c / c.ewm(span=n, adjust=False).mean() - 1
    ma, sd = c.rolling(20).mean(), c.rolling(20).std()
    f["bb_pos"] = (c - ma) / (2 * sd)
    f["bb_width"] = 4 * sd / ma
    f["vol_z"] = (v - v.rolling(96).mean()) / v.rolling(96).std()
    f["range_pct"] = (df["high"] - df["low"]) / c
    hour = df.index.hour + df.index.minute / 60
    f["hour_sin"] = np.sin(2 * np.pi * hour / 24)
    f["hour_cos"] = np.cos(2 * np.pi * hour / 24)
    f["dow"] = df.index.day_of_week
    return f.replace([np.inf, -np.inf], np.nan)


def build_features(df: pd.DataFrame) -> pd.DataFrame:
    """Shifted (look-ahead-free) feature matrix aligned to ``df.index``."""
    return raw_features(df).shift(1)[FEATURE_COLUMNS]


def make_labels(df: pd.DataFrame, feats: pd.DataFrame, horizon: int, k: float) -> pd.Series:
    """Class 2 (up) / 0 (down) / 1 (flat); NaN where the outcome is not yet resolved.

    Entry is the open of candle t, outcome is the close of candle t+horizon-1, and the move
    is normalised by the (shifted, therefore known-at-entry) ATR percentage.
    """
    fwd = df["close"].shift(-(horizon - 1)) / df["open"] - 1
    z = fwd / feats["atr_pct"]
    y = pd.Series(1.0, index=df.index)
    y[z > k] = 2.0
    y[z < -k] = 0.0
    y[z.isna()] = np.nan
    return y
