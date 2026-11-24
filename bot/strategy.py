"""Turn model probabilities into trade decisions (shared by backtest, paper and live)."""

from __future__ import annotations

from .config import Settings


def raw_signal(p_down: float, p_up: float, cfg: Settings) -> int:
    """Model direction regardless of what the market allows: +1 up, -1 down, 0 none."""
    if p_up != p_up or p_down != p_down:  # NaN guard
        return 0
    if p_up >= cfg.p_enter and p_up - p_down >= cfg.p_margin:
        return 1
    if p_down >= cfg.p_enter and p_down - p_up >= cfg.p_margin:
        return -1
    return 0


def decide(p_down: float, p_up: float, cfg: Settings) -> int:
    """ENTRY decision: +1 long, -1 short, 0 stay out. Shorts are suppressed on spot (no shorting)."""
    s = raw_signal(p_down, p_up, cfg)
    return 0 if (s < 0 and not cfg.allow_short) else s


def should_exit_on_flip(side: int, p_down: float, p_up: float, cfg: Settings) -> bool:
    """Exit early when the model now confidently points the other way. Uses the RAW signal so a
    long spot position still exits on a bearish flip even though shorting is not allowed."""
    return raw_signal(p_down, p_up, cfg) == -side
