"""Market-data feeds: LiveFeed (public Delta India REST) and ReplayFeed (historical clock)."""

from __future__ import annotations

import pandas as pd

from .broker.base import Feed
from .config import Settings
from .data import COLUMNS, rows_to_frame, source_exchange, source_symbol, validate_candles

# Verified against Delta India's public market list on 2026-11-24 (ccxt ``contractSize``).
DEFAULT_CONTRACT_SIZE = {"BTC/USD:USD": 0.001, "ETH/USD:USD": 0.01, "SOL/USD:USD": 1.0}


# Typical spot lot steps (units of the coin). ASSUMPTION - verify per exchange before real trading.
SPOT_STEP = {"BTC/USD:USD": 0.00001, "ETH/USD:USD": 0.0001, "SOL/USD:USD": 0.01}


class LiveFeed(Feed):
    """Signal prices come from ``cfg.data_source`` (Binance by default), see Settings."""

    def __init__(self, cfg: Settings, exchange=None):
        self.cfg = cfg
        self.ex = exchange or source_exchange(cfg)
        self.ex.load_markets()
        self.tf = pd.Timedelta(minutes=cfg.tf_minutes)

    def ohlcv_closed(self, symbol: str, limit: int) -> pd.DataFrame:
        sym, tf_ms = source_symbol(self.cfg, symbol), int(self.tf.total_seconds() * 1000)
        end = int(self.now().timestamp() * 1000)
        cursor, rows = end - (limit + 1) * tf_ms, []
        while cursor < end:  # paginate: exchanges cap one page at ~1000 candles
            chunk = self.ex.fetch_ohlcv(sym, self.cfg.timeframe, since=cursor, limit=1000)
            if not chunk:
                break
            rows.extend(chunk)
            cursor = chunk[-1][0] + tf_ms
            if len(chunk) < 1000:
                break
        df = rows_to_frame(rows)
        df = df[df.index + self.tf <= self.now()].tail(limit)
        df, dropped = validate_candles(df)
        return df if not dropped else df.iloc[0:0]  # any invalid candle -> no signal this cycle

    def last_price(self, symbol: str) -> float:
        return float(self.ex.fetch_ticker(source_symbol(self.cfg, symbol))["last"])

    def range_since(self, symbol: str, since: pd.Timestamp) -> list[tuple[float, float]]:
        ms = int((since.floor("1min") - pd.Timedelta(minutes=1)).timestamp() * 1000)
        rows = self.ex.fetch_ohlcv(source_symbol(self.cfg, symbol), "1m", since=ms, limit=500)
        return [(float(r[2]), float(r[3])) for r in rows]

    def contract_size(self, symbol: str) -> float:
        if self.cfg.market == "spot":  # spot trades in fractional units; step sizes are ASSUMPTIONS
            return float(SPOT_STEP[symbol])
        return float(DEFAULT_CONTRACT_SIZE[symbol])

    def now(self) -> pd.Timestamp:
        return pd.Timestamp.now(tz="UTC")


class ReplayFeed(Feed):
    """Deterministic clock over cached candles. ``set_time(ts)`` = candle ``ts`` just opened."""

    def __init__(self, data: dict[str, pd.DataFrame], cfg: Settings,
                 contract_sizes: dict[str, float] | None = None):
        self.data, self.cfg = data, cfg
        self.cs = contract_sizes or DEFAULT_CONTRACT_SIZE
        self.tf = pd.Timedelta(minutes=cfg.tf_minutes)
        self.ts: pd.Timestamp = next(iter(data.values())).index[0]

    def set_time(self, ts: pd.Timestamp) -> None:
        self.ts = ts

    def ohlcv_closed(self, symbol: str, limit: int) -> pd.DataFrame:
        d = self.data[symbol]
        return d[d.index < self.ts].tail(limit)[COLUMNS]

    def last_price(self, symbol: str) -> float:
        d = self.data[symbol]
        if self.ts in d.index:
            return float(d.at[self.ts, "open"])
        return float(d[d.index < self.ts]["close"].iloc[-1])

    def range_since(self, symbol: str, since: pd.Timestamp) -> list[tuple[float, float]]:
        d = self.data[symbol]
        w = d[(d.index >= since) & (d.index < self.ts)]
        return list(zip(w["high"].astype(float), w["low"].astype(float)))

    def contract_size(self, symbol: str) -> float:
        return float(self.cs[symbol])

    def now(self) -> pd.Timestamp:
        return self.ts
