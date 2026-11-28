"""Summaries built from the fills ledger (works for paper, replay and live)."""

from __future__ import annotations

import math
from .config import Settings


def round_trips(fills: list[dict]) -> list[dict]:
    """Group fills into round trips per symbol. net = sum(realized) - sum(fees)."""
    open_: dict[str, dict] = {}
    out: list[dict] = []
    for f in fills:
        s = f["symbol"]
        qty = float(f["qty"])
        if not all(math.isfinite(float(f[k])) for k in ("qty", "price", "fee", "realized_pnl")) or qty <= 0:
            raise ValueError("invalid fill in performance evidence")
        if f["reason"] == "entry":
            if s in open_:
                t = open_[s]
                if t["side"] != ("long" if f["side"] == "buy" else "short"):
                    raise ValueError("conflicting entry sides in ledger")
                total = t["remaining"] + qty
                t["entry"] = (t["entry"] * t["remaining"] + f["price"] * qty) / total
                t["remaining"] = total
                t["qty"] += qty
                t["net"] -= f["fee"]
                continue
            open_[s] = {"symbol": s, "open_ts": f["ts"], "side": "long" if f["side"] == "buy" else "short",
                        "entry": f["price"], "net": -f["fee"], "qty": qty, "remaining": qty}
        elif s in open_:
            t = open_[s]
            close_side = "sell" if t["side"] == "long" else "buy"
            if f["side"] != close_side or qty > t["remaining"] + 1e-9:
                raise ValueError("exit exceeds recorded position")
            t["net"] += f["realized_pnl"] - f["fee"]
            t["remaining"] -= qty
            t.update(close_ts=f["ts"], exit=f["price"], reason=f["reason"])
            if t["remaining"] <= 1e-9:
                open_.pop(s)
                t.pop("remaining")
                out.append(t)
        else:  # exit without a recorded entry (e.g. reconcile)
            out.append({"symbol": s, "open_ts": None, "side": "?", "entry": None, "qty": f["qty"],
                        "net": f["realized_pnl"] - f["fee"], "close_ts": f["ts"], "exit": f["price"],
                        "reason": f["reason"]})
    return out


def summarise(fills: list[dict], cfg: Settings, equity: float | None = None) -> dict:
    trips = round_trips(fills)
    nets = [t["net"] for t in trips]
    wins = sum(n for n in nets if n > 0)
    losses = -sum(n for n in nets if n < 0)
    fees = sum(f["fee"] for f in fills)
    reasons: dict[str, int] = {}
    for t in trips:
        reasons[t["reason"]] = reasons.get(t["reason"], 0) + 1
    # 30% flat tax on gains, losses cannot be set off (Sec 115BBH) -> tax on positive trades only
    tax_inr = wins * cfg.usdt_inr * 0.30
    return {
        "fills": len(fills),
        "round_trips": len(trips),
        "net_pnl_usd": round(sum(nets), 2),
        "win_rate_pct": round(100 * sum(n > 0 for n in nets) / len(nets), 1) if nets else 0.0,
        "profit_factor": round(wins / losses, 2) if losses > 0 else None,
        "fees_paid_usd": round(fees, 2),
        "exit_reasons": reasons,
        "equity_usd": None if equity is None else round(equity, 2),
        "est_tax_30pct_inr": round(tax_inr),
        "note": "Tax is an ESTIMATE; confirm TDS/tax treatment of futures with a chartered accountant.",
    }
