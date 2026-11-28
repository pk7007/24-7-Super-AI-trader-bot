"""Historical candle download (public Delta India endpoint) and CSV cache."""

from __future__ import annotations

import logging
import time
from pathlib import Path

import ccxt
import numpy as np
import pandas as pd

from .config import Settings

COLUMNS = ["open", "high", "low", "close", "volume"]
log = logging.getLogger("data")

# Binance public market-data hosts, tried in order. data-api.binance.vision serves market data only.
BINANCE_HOSTS = ("https://api.binance.com", "https://data-api.binance.vision", "https://api-gcp.binance.com")


class ResilientExchange:
    """Wraps a public ccxt Binance client. A network error (dropped TLS connection, timeout, 5xx,
    rate limit) is retried with back-off on the next host; the host that works is kept. Real errors
    (bad symbol, bad request) are raised at once. After ``attempts`` failures the error is raised, so
    the caller fails safe exactly as before (no data -> no trade) and the alert still fires."""

    def __init__(self, ex, hosts: tuple[str, ...] = BINANCE_HOSTS, attempts: int = 4,
                 backoff: tuple[float, ...] = (2, 5, 10), sleep=time.sleep):
        self.ex, self.hosts, self.attempts, self.backoff, self.sleep = ex, hosts, attempts, backoff, sleep
        self.host_i = 0
        self._set_host()

    def _set_host(self) -> None:
        # public endpoints only; signed calls (never used here) are not redirected to a data-only mirror
        self.ex.urls["api"]["public"] = self.hosts[self.host_i % len(self.hosts)] + "/api/v3"

    def _call(self, name: str, *a, **k):
        for i in range(self.attempts):
            try:
                return getattr(self.ex, name)(*a, **k)
            except (ccxt.DDoSProtection, ccxt.RateLimitExceeded) as e:  # 418/429 ban: other hosts share the limit
                log.error("%s: rate limited (%s); not retrying, to avoid extending a ban", name, type(e).__name__)
                raise
            except ccxt.NetworkError as e:
                if i == self.attempts - 1:
                    log.error("%s failed after %d attempts on all hosts: %s", name, self.attempts, type(e).__name__)
                    raise
                old = self.hosts[self.host_i % len(self.hosts)]
                self.host_i += 1
                self._set_host()
                wait = self.backoff[min(i, len(self.backoff) - 1)]
                log.warning("%s: %s on %s; retry %d/%d on %s in %ss", name, type(e).__name__, old, i + 1,
                            self.attempts - 1, self.hosts[self.host_i % len(self.hosts)], wait)
                self.sleep(wait)

    def fetch_ohlcv(self, *a, **k):
        return self._call("fetch_ohlcv", *a, **k)

    def fetch_ticker(self, *a, **k):
        return self._call("fetch_ticker", *a, **k)

    def load_markets(self, *a, **k):
        return self._call("load_markets", *a, **k)

    def __getattr__(self, name):  # everything else (parse_timeframe, options, id...) passes through
        if name == "ex" or name.startswith("__"):  # avoid recursion during copy/unpickle
            raise AttributeError(name)
        return getattr(self.ex, name)


def make_public_exchange(cfg: Settings) -> ccxt.delta:
    ex = ccxt.delta({"timeout": 20000, "enableRateLimit": True})
    ex.urls["api"] = {"public": cfg.api_base, "private": cfg.api_base}
    return ex


def make_reference_exchange() -> ResilientExchange:
    ex = ccxt.binance({"timeout": 20000, "enableRateLimit": True})
    ex.options["fetchMarkets"] = {**ex.options.get("fetchMarkets", {}), "types": ["spot"]}  # signals use spot only
    return ResilientExchange(ex)


def source_exchange(cfg: Settings):
    return make_reference_exchange() if cfg.data_source == "binance" else make_public_exchange(cfg)


def source_symbol(cfg: Settings, symbol: str) -> str:
    """BTC/USD:USD (Delta perp) -> BTC/USDT (Binance) when Binance is the signal source."""
    return f"{symbol.split('/')[0]}/USDT" if cfg.data_source == "binance" else symbol


def validate_candles(df: pd.DataFrame, max_move: float = 0.25) -> tuple[pd.DataFrame, int]:
    """Drop structurally impossible candles; return (clean_frame, rows_dropped)."""
    px = df[["open", "high", "low", "close"]]
    bad = (px <= 0).any(axis=1) | (df["high"] < df["low"]) | (df["volume"] < 0)
    bad |= ~np.isfinite(df[COLUMNS]).all(axis=1)
    bad |= ((df["open"] > df["high"]) | (df["open"] < df["low"])
            | (df["close"] > df["high"]) | (df["close"] < df["low"]))
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
