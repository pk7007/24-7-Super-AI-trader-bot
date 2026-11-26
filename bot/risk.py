"""Position sizing, stop/target maths and the daily kill-switch (RULE 4)."""

from __future__ import annotations

import math
from dataclasses import dataclass

from .config import Settings


def stop_price(side: int, entry: float, atr_pct: float, cfg: Settings) -> float:
    return entry * (1 - side * cfg.stop_atr * atr_pct)


def tp_price(side: int, entry: float, atr_pct: float, cfg: Settings) -> float:
    return entry * (1 + side * cfg.tp_atr * atr_pct)


def round_trip_cost_pct(cfg: Settings) -> float:
    """Fees on both legs (incl. GST) plus entry slippage and stop slippage, as a fraction of notional."""
    return 2 * cfg.taker_fee * cfg.gst + cfg.slippage + cfg.stop_slippage


def position_units(equity: float, price: float, atr_pct: float, cfg: Settings) -> float:
    """Base-asset units so that hitting the stop loses at most ``risk_per_trade`` of equity
    INCLUDING fees and slippage (a stop-out pays both legs), capped by ``max_leverage``."""
    if equity <= 0 or price <= 0 or not atr_pct or atr_pct != atr_pct or atr_pct <= 0:
        return 0.0
    stop_dist = cfg.stop_atr * atr_pct
    notional = equity * cfg.risk_per_trade / (stop_dist + round_trip_cost_pct(cfg))
    notional = min(notional, equity * cfg.max_leverage)
    return notional / price


def to_contracts(units: float, contract_size: float, min_contracts: float = 1.0) -> int:
    """Exchange contracts are integers; round DOWN so risk is never exceeded."""
    n = math.floor(units / contract_size)
    return n if n >= min_contracts else 0


@dataclass
class DailyKillSwitch:
    """Tracks UTC-day starting equity. ``breached`` is True once drawdown >= limit."""

    limit: float
    day: str = ""
    start_equity: float = 0.0
    halted: bool = False

    def roll(self, day: str, equity: float) -> bool:
        """Start a new UTC day. Returns True if the day changed."""
        if day != self.day:
            self.day, self.start_equity, self.halted = day, equity, False
            return True
        return False

    def drawdown(self, equity: float) -> float:
        if self.start_equity <= 0:
            return 0.0
        return equity / self.start_equity - 1

    def check(self, equity: float) -> bool:
        """True when this call newly trips the switch."""
        if not self.halted and self.drawdown(equity) <= -self.limit:
            self.halted = True
            return True
        return False
