"""Multiple-testing correction for backtests: the Deflated Sharpe Ratio (DSR).

Bailey & Lopez de Prado (2014), "The Deflated Sharpe Ratio". Trying many strategies and settings and keeping the
best one inflates its Sharpe. DSR is the probability that the true Sharpe is above the Sharpe you would expect
from the BEST of ``n_trials`` strategies with no skill, given the variance of Sharpe across the trials, the track
record length and the non-normality (skew, kurtosis) of the returns. A common bar is DSR >= 0.95.
All Sharpe values here are per period (daily), not annualised.
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from statistics import NormalDist

import pandas as pd

EULER_GAMMA = 0.5772156649015329
_N = NormalDist()


def sharpe_stats(returns: pd.Series) -> dict:
    """Per-period Sharpe, skew and NON-excess kurtosis (normal = 3) of a return series."""
    r = pd.Series(returns, dtype=float).dropna()
    sd = float(r.std())
    return {"sr": float(r.mean()) / sd if sd > 0 else 0.0, "t": int(len(r)),
            "skew": float(r.skew()) if len(r) > 2 else 0.0, "kurt": float(r.kurt()) + 3.0 if len(r) > 3 else 3.0}


def expected_max_sharpe(var_sr: float, n_trials: int) -> float:
    """Expected maximum Sharpe among ``n_trials`` skill-less trials whose Sharpe variance is ``var_sr``."""
    if n_trials <= 1 or var_sr <= 0:
        return 0.0
    return math.sqrt(var_sr) * ((1 - EULER_GAMMA) * _N.inv_cdf(1 - 1 / n_trials)
                                + EULER_GAMMA * _N.inv_cdf(1 - 1 / (n_trials * math.e)))


def deflated_sharpe(sr: float, t: int, skew: float, kurt: float, var_sr: float, n_trials: int) -> dict:
    sr0 = expected_max_sharpe(var_sr, n_trials)
    denom = 1 - skew * sr + (kurt - 1) / 4 * sr ** 2
    z = (sr - sr0) * math.sqrt(max(t - 1, 1)) / math.sqrt(denom) if denom > 0 else float("-inf")
    return {"dsr": _N.cdf(z) if math.isfinite(z) else 0.0, "sr0": sr0, "sr": sr, "t": t,
            "n_trials": n_trials, "var_sr": var_sr, "skew": skew, "kurt": kurt}


def count_lab_trials(reports: Path, extra: int = 0, skip: str | None = None) -> int:
    """Every parameter setting of every candidate in every ``lab*.json`` report counts as one trial (conservative:
    fee-stress and limit reruns count too). Holdout reports are out-of-sample tests, not selections, so excluded.
    ``extra`` adds trials made outside the lab (the rejected LightGBM model); ``skip`` names a report being rerun."""
    n = 0
    for p in sorted(Path(reports).glob("lab*.json")):
        if skip and p.stem == skip:
            continue
        try:
            cands = json.loads(p.read_text()).get("candidates", {})
        except (OSError, ValueError):
            continue
        n += sum(len(c.get("param_variant_returns_pct", [])) or 1 for c in cands.values())
    return n + extra
