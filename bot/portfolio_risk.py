"""Portfolio-level entry checks, run after a position is sized and before the order is sent.

1. Gross exposure: open positions plus the new one may not exceed ``max_leverage`` x equity (1x on spot).
2. Expected Shortfall: the 1-day 97.5% historical-simulation ES of the WHOLE portfolio after the entry may not
   exceed ``max_es_pct`` of equity. It is computed from the coins' joint daily returns, so correlation is counted:
   two coins that fall together add up, coins that do not diversify. It ignores stops on purpose (gaps and
   exchange outages skip stops), so it is a ceiling against tail risk, not a forecast.

Only closed daily candles are used (RULE 1). Any failure to get history refuses the entry (fail closed). With
fewer than ``MIN_DAYS`` of history the entry is refused, except in replay, where the check is skipped and logged.
These checks can only block an entry; they never open, resize or close a position.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import math
from typing import Callable

import pandas as pd

from .config import Settings

MIN_DAYS = 30


@dataclass
class Verdict:
    ok: bool
    reason: str
    gross: float = 0.0
    var99: float | None = None
    es: float | None = None
    corr: dict[str, float] = field(default_factory=dict)


def daily_returns(closes: dict[str, pd.Series]) -> pd.DataFrame:
    """Simple daily returns on the dates every coin has a close."""
    return pd.DataFrame(closes).sort_index().dropna().pct_change().dropna()


def es_var(values: dict[str, float], rets: pd.DataFrame, alpha: float = 0.975) -> tuple[float, float]:
    """1-day historical VaR(99%) and ES(alpha) in USD for signed position values (long > 0)."""
    pnl = rets[list(values)].mul(pd.Series(values)).sum(axis=1)
    losses = (-pnl).sort_values()
    var99 = float(losses.quantile(0.99))
    k = max(1, int(round(len(losses) * (1 - alpha))))  # number of worst days in the tail
    es = float(losses.iloc[-k:].mean())
    return var99, es


def check_entry(held: dict[str, float], sym: str, value: float, equity: float,
                daily_closes: Callable[[str, int], pd.Series], cfg: Settings) -> Verdict:
    """``held`` and ``value`` are signed USD position values. Returns whether the entry may proceed."""
    if not all(math.isfinite(v) for v in (equity, value, *held.values())) or equity <= 0:
        return Verdict(False, "nonfinite or invalid equity/exposure; entry refused")
    gross = sum(abs(v) for v in held.values()) + abs(value)
    if equity <= 0 or gross > cfg.max_leverage * equity * (1 + 1e-9):
        return Verdict(False, f"gross exposure {gross:.2f} > {cfg.max_leverage:g}x equity {equity:.2f}", gross)
    syms = [*held, sym]
    try:
        closes = {s: daily_closes(s, cfg.es_lookback_days) for s in syms}
    except Exception as exc:  # noqa: BLE001 - no history, no entry
        return Verdict(False, f"history unavailable ({type(exc).__name__}); entry refused", gross)
    if any(s.empty or not all(math.isfinite(v) and v > 0 for v in s) for s in closes.values()):
        return Verdict(False, "invalid daily history; entry refused", gross)
    rets = daily_returns(closes)
    if len(rets) < MIN_DAYS:
        if cfg.mode == "replay":
            return Verdict(True, f"ES check skipped: only {len(rets)} days of history (replay)", gross)
        return Verdict(False, f"only {len(rets)} days of history (< {MIN_DAYS}); entry refused", gross)
    var99, es = es_var({**held, sym: value}, rets)
    if not all(math.isfinite(v) for v in (var99, es)):
        return Verdict(False, "nonfinite portfolio risk; entry refused", gross)
    corr = {h: round(float(rets[sym].corr(rets[h])), 2) for h in held}
    if es > cfg.max_es_pct * equity:
        return Verdict(False, f"1-day expected shortfall {es:.2f} > {cfg.max_es_pct:.1%} of equity "
                              f"({cfg.max_es_pct * equity:.2f})", gross, var99, es, corr)
    return Verdict(True, f"ES {es:.2f} ({es / equity:.2%} of equity), VaR99 {var99:.2f}", gross, var99, es, corr)
