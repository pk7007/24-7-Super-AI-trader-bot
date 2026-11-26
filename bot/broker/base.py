"""Broker + market-feed interfaces and shared records."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

import pandas as pd


@dataclass
class Fill:
    ts: str  # ISO UTC
    symbol: str
    side: str  # "buy" | "sell"
    qty: float  # contracts
    price: float
    fee: float  # quote currency (USD), includes GST if configured
    realized_pnl: float  # gross PnL of the closing portion (0 for opening fills)
    reason: str
    order_id: str


@dataclass
class ExPosition:
    symbol: str
    side: int
    contracts: float
    entry: float


def closed_days(candles: pd.DataFrame, now: pd.Timestamp) -> pd.Series:
    """Daily closes (last intraday close of each UTC day) for days that ended at or before ``now``."""
    if candles.empty:
        return pd.Series(dtype=float)
    daily = candles["close"].resample("1D").last().dropna()
    return daily[daily.index + pd.Timedelta(days=1) <= now]


class Feed(ABC):
    """Market data. Implementations: LiveFeed (public REST) and ReplayFeed (history)."""

    @abstractmethod
    def ohlcv_closed(self, symbol: str, limit: int) -> pd.DataFrame: ...

    @abstractmethod
    def last_price(self, symbol: str) -> float: ...

    @abstractmethod
    def range_since(self, symbol: str, since: pd.Timestamp) -> list[tuple[float, float]]:
        """(high, low) pairs of price action since ``since`` in time order."""

    def daily_closes(self, symbol: str, days: int) -> pd.Series:
        """Closes of the last ``days`` CLOSED UTC days (the forming day is never included). Default: from candles."""
        df = self.ohlcv_closed(symbol, days * 96 + 96)
        return closed_days(df, self.now()).tail(days)

    @abstractmethod
    def contract_size(self, symbol: str) -> float: ...

    @abstractmethod
    def now(self) -> pd.Timestamp: ...


class Broker(ABC):
    @abstractmethod
    def equity(self) -> float: ...

    @abstractmethod
    def positions(self) -> dict[str, ExPosition]: ...

    @abstractmethod
    def market_order(self, symbol: str, side: str, contracts: float, reduce_only: bool = False,
                     reason: str = "") -> Fill | None: ...

    @abstractmethod
    def place_stop(self, symbol: str, side: str, contracts: float, stop_price: float) -> str:
        """Reduce-only stop-market order resting ON THE EXCHANGE. ``side`` = closing side."""

    @abstractmethod
    def cancel_order(self, symbol: str, order_id: str) -> None: ...

    @abstractmethod
    def open_stop_ids(self, symbol: str) -> set[str]: ...

    @abstractmethod
    def drain_fills(self) -> list[Fill]:
        """Fills that happened without the bot calling market_order (i.e. stops)."""

    @abstractmethod
    def tick(self) -> None:
        """Paper: evaluate resting stops. Live: no-op."""
