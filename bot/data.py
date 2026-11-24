"""Historical candle download (public Delta India endpoint) and CSV cache."""

from __future__ import annotations

import time
from pathlib import Path

import ccxt
import pandas as pd

from .config import Settings

COLUMNS = ["open", "high", "low", "close", "volume"]


def make_public_exchange(cfg: Settings) -> ccxt.delta:
    ex = ccxt.delta({"timeout": 20000, "enableRateLimit": True})
    ex.urls["api"] = {"public": cfg.api_base, "private": cfg.api_base}
    return ex


def make_reference_exchange() -> ccxt.binance:
    return ccxt.binance({"timeout": 20000, "enableRateLimit": True})


def source_exchange(cfg: Settings):
    return make_reference_exchange() if cfg.data_source == "binance" else make_public_exchange(cfg)


def source_symbol(cfg: Settings, symbol: str) -> str:
    """BTC/USD:USD (Delta perp) -> BTC/USDT (Binance) when Binance is the signal source."""
    return f"{symbol.split('/')[0]}/USDT" if cfg.data_source == "binance" else symbol


def validate_candles(df: pd.DataFrame, max_move: float = 0.25) -> tuple[pd.DataFrame, int]:
    """Drop structurally impossible candles; return (clean_frame, rows_dropped)."""
    px = df[["open", "high", "low", "close"]]
    bad = (px <= 0).any(axis=1) | (df["high"] < df["low"]) | (df["volume"] < 0)
    bad |= (df["close"].pct_change().abs() > max_move) | ((df["high"] / df["low"] - 1) > max_move)
    return df[~bad], int(bad.sum())


def rows_to_frame(rows: list[list[float]]) -> pd.DataFrame:
    df = pd.DataFrame(rows, columns=["ts", *COLUMNS])
    df["date"] = pd.to_datetime(df["ts"], unit="ms", utc=True)
    df = df.drop(columns="ts").drop_duplicates("date").set_index("date").sort_index()
    return df.astype(float)


def csv_path(cfg: Settings, symbol: str) -> Path:
    return cfg.data_dir / f"{symbol.split('/')[0]}_{cfg.timeframe}_{cfg.data_source}.csv"


def fetch_history(ex, symbol: str, timeframe: str, since_ms: int, until_ms: int | None = None,
                  page: int = 1000) -> pd.DataFrame:
    """Paginate ``fetch_ohlcv`` forward from ``since_ms``. Closed candles only."""
    tf_ms = ex.parse_timeframe(timeframe) * 1000
    until_ms = until_ms or int(time.time() * 1000)
    rows: list[list[float]] = []
    cursor = since_ms
    while cursor < until_ms:
        chunk = ex.fetch_ohlcv(symbol, timeframe, since=cursor, limit=page)
        if not chunk:
            if rows:  # reached the end of available data
                break
            cursor += page * tf_ms  # history starts later than requested: skip the empty window
            continue
        rows.extend(chunk)
        last = chunk[-1][0]
        if last + tf_ms <= cursor:
            break
        cursor = last + tf_ms
        if len(chunk) < 2:
            break
    df = rows_to_frame(rows)
    # drop the still-forming candle
    return df[df.index.view("int64") // 10**6 + tf_ms <= until_ms] if len(df) else df


def load_or_fetch(cfg: Settings, symbol: str, days: int, refresh: bool = False) -> pd.DataFrame:
    cfg.data_dir.mkdir(parents=True, exist_ok=True)
    path = csv_path(cfg, symbol)
    ex, sym = source_exchange(cfg), source_symbol(cfg, symbol)
    now_ms = int(time.time() * 1000)
    if path.exists() and not refresh:
        old = pd.read_csv(path, index_col="date", parse_dates=["date"])
        old.index = pd.to_datetime(old.index, utc=True)
        since = int(old.index[-1].timestamp() * 1000) + 1
        new = fetch_history(ex, sym, cfg.timeframe, since, now_ms)
        df = pd.concat([old, new]).loc[lambda d: ~d.index.duplicated()].sort_index()
    else:
        df = fetch_history(ex, sym, cfg.timeframe, now_ms - days * 86_400_000, now_ms)
    df, dropped = validate_candles(df)
    if dropped:
        print(f"{symbol}: dropped {dropped} invalid candles")
    df.to_csv(path)
    return df


def read_cached(cfg: Settings, symbol: str) -> pd.DataFrame:
    df = pd.read_csv(csv_path(cfg, symbol), index_col="date", parse_dates=["date"])
    df.index = pd.to_datetime(df.index, utc=True)
    return df
