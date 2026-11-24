"""Summaries built from the fills ledger (works for paper, replay and live)."""

from __future__ import annotations

from .config import Settings


def round_trips(fills: list[dict]) -> list[dict]:
    """Group fills into round trips per symbol. net = sum(realized) - sum(fees)."""
    open_: dict[str, dict] = {}
    out: list[dict] = []
    for f in fills:
        s = f["symbol"]
        if f["reason"] == "entry":
            open_[s] = {"symbol": s, "open_ts": f["ts"], "side": "long" if f["side"] == "buy" else "short",
                        "entry": f["price"], "net": -f["fee"], "qty": f["qty"]}
        elif s in open_:
            t = open_.pop(s)
            t["net"] += f["realized_pnl"] - f["fee"]
            t.update(close_ts=f["ts"], exit=f["price"], reason=f["reason"])
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
