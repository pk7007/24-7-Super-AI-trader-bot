"""Capital feasibility: can a given capital economically run the spot trend strategy?

Every input that is an ASSUMPTION (not verified from an exchange) is a named parameter and is
printed in the report. The system must REFUSE trades it cannot size within its own risk budget.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from .config import ROOT, Settings
from .features import atr

CAPITALS_INR = [1_000, 2_500, 5_000, 10_000, 25_000, 50_000, 100_000, 500_000]


@dataclass(frozen=True)
class Assumptions:
    risk_per_trade: float = 0.005  # master prompt: 0.25%-0.5%
    stop_atr: float = 2.0
    min_order_inr: float = 100.0  # ASSUMPTION - spot minimum notional differs per exchange/pair; verify
    max_open_positions: int = 3
    tds_rate: float = 0.01  # Sec 194S, on sale value - verify current rate/thresholds with a CA
    tax_rate: float = 0.30  # Sec 115BBH flat tax on gains, no loss set-off - verify with a CA


def daily_atr_pct(df: pd.DataFrame) -> float:
    a = atr(df, 96 * 14) / df["close"] * np.sqrt(96)
    return float(a.dropna().median())


def row(capital: float, stop_dist: float, cfg: Settings, a: Assumptions) -> dict:
    notional = capital * a.risk_per_trade / stop_dist
    notional = min(notional, capital * cfg.max_leverage / a.max_open_positions)  # no leverage, 3 slots
    round_trip_cost = 2 * (cfg.taker_fee * cfg.gst + cfg.slippage)
    feasible = notional >= a.min_order_inr
    return {
        "capital_inr": capital,
        "risk_budget_inr": round(capital * a.risk_per_trade, 2),
        "position_notional_inr": round(notional),
        "meets_min_order": feasible,
        "round_trip_cost_inr": round(notional * round_trip_cost, 2),
        "round_trip_cost_pct": round(round_trip_cost * 100, 3),
        "tds_withheld_per_sale_inr": round(notional * a.tds_rate, 2),
        "break_even_move_pct": round((round_trip_cost) * 100, 3),
        "verdict": "OK" if feasible else "REFUSE: risk budget cannot reach the minimum order",
    }


def build_report(cfg: Settings, btc: pd.DataFrame, a: Assumptions = Assumptions()) -> tuple[list[dict], str]:
    stop_dist = a.stop_atr * daily_atr_pct(btc)
    rows = [row(c, stop_dist, cfg, a) for c in CAPITALS_INR]
    md = ["# Capital feasibility (spot, long-only, no leverage)", "",
          f"Stop distance = {a.stop_atr} x daily ATR = **{stop_dist:.2%}** (median BTC, from data). "
          f"Risk/trade {a.risk_per_trade:.2%}. Costs: taker {cfg.taker_fee:.2%} x GST {cfg.gst} + slippage {cfg.slippage:.2%} per side.",
          f"ASSUMPTIONS to verify: min order Rs {a.min_order_inr:.0f}; TDS {a.tds_rate:.0%} of sale value; tax {a.tax_rate:.0%} on gains.", "",
          "| Capital (INR) | Risk budget | Position size | Min order met | Round-trip cost | TDS per sale | Verdict |",
          "|---:|---:|---:|:--:|---:|---:|---|"]
    for r in rows:
        md.append(f"| {r['capital_inr']:,} | {r['risk_budget_inr']} | {r['position_notional_inr']:,} | "
                  f"{'yes' if r['meets_min_order'] else 'NO'} | {r['round_trip_cost_inr']} ({r['round_trip_cost_pct']}%) | "
                  f"{r['tds_withheld_per_sale_inr']} | {r['verdict']} |")
    md += ["", "No daily profit target is implied. See BACKTEST_REPORT.md for return *distributions*."]
    return rows, "\n".join(md)


def run(cfg: Settings) -> str:
    from .data import read_cached

    rows, md = build_report(cfg, read_cached(cfg, "BTC/USD:USD"))
    out = ROOT / "reports"
    out.mkdir(exist_ok=True)
    (out / "feasibility.md").write_text(md, encoding="utf-8")
    return md
