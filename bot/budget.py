"""crypto-budget: how big can this trade be, which limit decided it, in USD and INR.

Wraps the bot's own sizing (``risk.position_units`` + ``risk.to_contracts`` + the spot lot steps), so the
number it prints is the number the bot would trade. It adds what the bot does not show: each limit's own
maximum, which one decided, a free-cash limit for spot, the capital needed to reach the minimum order, and
the ``crypto-risk`` verdict on the result (the skill chain: budget -> risk).

Read-only on bot state. ``--write`` writes one proposal to ``proposals/<mode>_order.json``; nothing is placed.

    python -m bot.budget --symbol BTC --price 95000 --stop 93000
    python -m bot.budget --symbol BTC --bot           # live price + the bot's own ATR stop (network)
    python -m bot.budget --symbol ETH --price 3000 --stop 2850 --json --write

Exit codes: 0 = a size that passes crypto-risk, 20 = refused/BLOCK, 2 = usage error.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from dataclasses import asdict, dataclass, replace

from .config import ROOT, Settings
from .feeds import DEFAULT_CONTRACT_SIZE, SPOT_STEP
from .risk import position_units, round_trip_cost_pct, stop_price, to_contracts
from .riskcheck import EXIT_BLOCK, EXIT_PASS, Context, Order, _match, _run_dir, evaluate, load_context
from .strategy import decide

BIG = 1e12  # stands in for "no cap" when isolating one limit


@dataclass
class Budget:
    symbol: str
    price: float
    stop: float
    qty: float  # final size, rounded DOWN to the lot step (0 = refused)
    decided_by: str  # which limit set the size, or why it is zero
    limits: dict  # limit name -> max qty under that limit alone (+ "bot_would_trade")
    usd: dict  # equity, free cash, risk budget, notional, loss at stop
    inr: dict  # same in rupees
    min_order: dict  # minimum, whether met, capital needed to meet it at this stop
    refused: list[str]
    risk_verdict: dict  # crypto-risk decision + reasons for exactly this order


def _pos(x) -> bool:
    return isinstance(x, (int, float)) and math.isfinite(x) and x > 0


def _step(symbol: str, cfg: Settings) -> float:
    return float(SPOT_STEP[symbol] if cfg.market == "spot" else DEFAULT_CONTRACT_SIZE[symbol])


def size(symbol: str, price: float, stop: float, ctx: Context, cfg: Settings) -> Budget:
    """Pure: no I/O. ``symbol`` must already be the bot's own symbol (see riskcheck._match).
    Any unexpected error becomes a refusal (fail closed), never an exception with another exit code."""
    try:
        return _size(symbol, price, stop, ctx, cfg)
    except Exception as e:  # noqa: BLE001
        why = [f"sizing failed: {type(e).__name__}: {e}"]
        return Budget(symbol, float("nan"), float("nan"), 0.0, "refused", {}, {}, {}, {}, why,
                      {"decision": "BLOCK", "reasons": why})


def _size(symbol: str, price: float, stop: float, ctx: Context, cfg: Settings) -> Budget:
    refused: list[str] = []
    if not (_pos(price) and _pos(stop)):
        refused.append(f"price/stop must be positive numbers (price={price!r}, stop={stop!r})")
    elif price == stop:
        refused.append("stop equals price")
    if not _pos(ctx.equity):
        refused.append(f"equity not a positive number ({ctx.equity!r})")
    refused += [f"state: {e}" for e in ctx.errors]
    if refused:
        return _done(symbol, price, stop, 0.0, "refused", {}, ctx, cfg, refused)

    eq = ctx.equity
    long_ = stop < price
    atr_equiv = abs(price - stop) / price / cfg.stop_atr  # the bot's position_units then sees exactly this stop
    step = _step(symbol, cfg)
    open_notional = sum(abs(p["coins"]) * p["entry"] for p in ctx.positions.values())  # coins, not bot units
    free_cash = eq - open_notional  # paper cash is not reduced by open positions; spot cannot spend it twice
    slots = cfg.max_positions - len(ctx.positions)

    limits = {"risk_per_trade": position_units(eq, price, atr_equiv, replace(cfg, max_leverage=BIG)),
              "max_leverage": eq * cfg.max_leverage / price}
    if cfg.market == "spot":
        limits["free_cash"] = max(free_cash, 0.0) / (price * (1 + cfg.taker_fee * cfg.gst + cfg.slippage))
    limits["open_slots"] = BIG if slots > 0 else 0.0
    decided_by = min(limits, key=limits.get)
    qty = to_contracts(limits[decided_by], step) * step
    if slots <= 0:
        refused.append(f"no open slot: {len(ctx.positions)} positions, limit {cfg.max_positions}")
    elif decided_by == "free_cash" and free_cash <= 0:
        refused.append(f"no free cash: open positions use ${open_notional:,.2f} of ${eq:,.2f}")
    elif qty <= 0:
        refused.append(f"size rounds to zero at lot step {step} (limit {decided_by})")
        decided_by = "lot_step"
    if qty > 0 and qty * price * cfg.usdt_inr < cfg.min_order_inr:
        refused.append(f"order Rs {qty * price * cfg.usdt_inr:.0f} below minimum Rs {cfg.min_order_inr:.0f}: the stop "
                       "is too far for this capital; refusing rather than over-risking")
        decided_by, qty = "min_order", 0.0
    b = _done(symbol, price, stop, qty, decided_by, limits, ctx, cfg, refused, long_, free_cash)
    b.limits["bot_would_trade"] = to_contracts(position_units(eq, price, atr_equiv, cfg), step) * step
    return b


def _done(symbol, price, stop, qty, decided_by, limits, ctx, cfg, refused, long_=True, free_cash=None) -> Budget:
    ok = _pos(price) and _pos(stop) and price != stop
    per_unit = abs(price - stop) + price * round_trip_cost_pct(cfg) if ok else None
    eq = ctx.equity if _pos(ctx.equity) else None
    usd = {"equity": eq, "free_cash": free_cash, "risk_budget": eq * cfg.risk_per_trade if eq else None,
           "notional": qty * price if ok else 0.0, "loss_at_stop_incl_costs": qty * per_unit if qty else 0.0}
    r = cfg.usdt_inr
    inr = {k: (round(v * r, 2) if isinstance(v, (int, float)) else None) for k, v in usd.items()}
    need = None
    if ok:
        # smallest lot-step quantity worth at least the minimum, then the equity whose risk budget buys it
        step = _step(symbol, cfg)
        q_min = math.ceil(cfg.min_order_inr / r / price / step - 1e-9) * step
        need = max(q_min * per_unit / cfg.risk_per_trade,  # the risk budget must buy q_min ...
                   q_min * price / cfg.max_leverage)  # ... and the 1x cap must allow it (open positions not counted)
    min_order = {"min_inr": cfg.min_order_inr, "met": bool(qty) and qty * price * r >= cfg.min_order_inr,
                 "capital_needed_usd": round(need, 2) if need else None,
                 "capital_needed_inr": round(need * r) if need else None}
    if qty > 0:
        v = evaluate(Order(symbol, "buy" if long_ else "sell", qty, price, stop), ctx, cfg)
        verdict = {"decision": v.decision, "reasons": v.reasons}
    else:
        verdict = {"decision": "BLOCK", "reasons": refused or ["size is zero"]}
    return Budget(symbol, price, stop, qty, decided_by, limits, usd, inr, min_order, refused, verdict)


def _clean(o):
    """JSON without bare NaN/inf (not valid JSON for other tools)."""
    if isinstance(o, float) and not math.isfinite(o):
        return None
    if isinstance(o, dict):
        return {k: _clean(v) for k, v in o.items()}
    if isinstance(o, list):
        return [_clean(v) for v in o]
    return o


# ---------------------------------------------------------------------------------------------- live mode
def bot_price_and_stop(symbol: str, cfg: Settings) -> tuple[float, float, float, str]:
    """Last closed price, the bot's own ATR and its stop, computed the way the engine does it now."""
    import pandas as pd

    from .feeds import LiveFeed
    from .main import get_model

    feed, model = LiveFeed(cfg), get_model(cfg)
    df = feed.ohlcv_closed(symbol, getattr(model, "lookback", 600))
    if len(df) < getattr(model, "min_candles", 300):
        raise RuntimeError(f"only {len(df)} valid candles for {symbol}; the bot would make no decision")
    tf = pd.Timedelta(minutes=cfg.tf_minutes)
    expected_last = feed.now().floor(f"{cfg.tf_minutes}min") - tf  # same freshness rule as engine._signal
    if df.index[-1] != expected_last:
        raise RuntimeError(f"stale candles for {symbol} (last {df.index[-1]}, expected {expected_last}); "
                           "the bot would skip this coin")
    last = float(df["close"].iloc[-1])
    nxt = df.index[-1] + pd.Timedelta(minutes=cfg.tf_minutes)
    ext = pd.concat([df, pd.DataFrame({"open": last, "high": last, "low": last, "close": last, "volume": 0.0},
                                      index=[nxt])])
    out = model.predict_from_candles(ext)
    if out is None or not math.isfinite(out[1]) or out[1] <= 0 or out[0].isna().any():
        raise RuntimeError(f"model gave no signal/ATR for {symbol}")
    p, atr = out[0], float(out[1])
    signal = {1: "BUY", -1: "SELL", 0: "stay out"}[decide(p["p_down"], p["p_up"], cfg)]
    price = float(feed.last_price(symbol))  # the engine sizes on the live ticker, not the candle close
    if not (math.isfinite(price) and price > 0):
        raise RuntimeError(f"bad live price for {symbol}: {price!r}")
    return price, stop_price(1, price, atr, cfg), atr, signal


def _fmt(b: Budget) -> str:
    u, i, m = b.usd, b.inr, b.min_order
    side = "sell (short)" if b.stop > b.price else "buy"
    head = f"{b.symbol}: {'REFUSED' if not b.qty else f'{side} {b.qty:.8g}'} @ {b.price:,.2f} stop {b.stop:,.2f}"
    lines = [head, f"  decided by: {b.decided_by}"]
    for k, v in b.limits.items():
        lines.append(f"   - {k:16s} {'no limit' if v >= BIG / 10 else f'{v:.8g}'}")
    lines.append(f"  notional ${u['notional']:,.2f} (Rs {i['notional'] or 0:,.0f}); loss at stop incl. costs "
                 f"${u['loss_at_stop_incl_costs']:,.4f} (Rs {i['loss_at_stop_incl_costs'] or 0:,.2f}); budget "
                 f"${u['risk_budget'] or 0:,.4f} (Rs {i['risk_budget'] or 0:,.2f})")
    lines.append(f"  minimum order Rs {m['min_inr']:.0f}: {'met' if m['met'] else 'NOT met'}; capital needed at "
                 f"this stop: Rs {m['capital_needed_inr'] or 0:,} (${m['capital_needed_usd']})")
    lines += [f"  refused: {r}" for r in b.refused]
    lines.append(f"  crypto-risk: {b.risk_verdict['decision']}"
                 + "".join(f"\n   - {r}" for r in b.risk_verdict["reasons"]))
    return "\n".join(lines)


def _proposal_path(mode: str):
    return ROOT / "proposals" / f"{mode}_order.json"


def _refuse(a, why: str) -> int:
    """Every refusal path: say why, and with --write remove an older proposal so it cannot look current."""
    print(f"REFUSED: {why}")
    p = _proposal_path(a.mode)
    if a.write and p.exists():
        p.unlink()
        print(f"  removed old proposal: {p}")
    return EXIT_BLOCK


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m bot.budget", description=__doc__.split("\n\n")[0])
    ap.add_argument("--symbol", required=True)
    ap.add_argument("--price", type=float)
    ap.add_argument("--stop", type=float)
    ap.add_argument("--bot", action="store_true", help="use the live price and the bot's own ATR stop")
    ap.add_argument("--mode", default="paper", choices=["paper", "shadow"])
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--write", action="store_true", help="write proposals/<mode>_order.json (nothing is placed)")
    a = ap.parse_args(argv)
    if a.bot and (a.price is not None or a.stop is not None):
        ap.error("--bot uses the live price and the bot's stop; do not also give --price/--stop")
    if not a.bot and (a.price is None or a.stop is None):
        ap.error("give --price and --stop, or --bot")

    import os
    os.environ.setdefault("STRATEGY", "ensemble")
    os.environ.setdefault("MARKET", "spot")
    os.environ["BOT_MODE"] = a.mode
    try:
        cfg = Settings.from_env()
    except Exception as e:  # noqa: BLE001 - fail closed with the BLOCK code
        return _refuse(a, f"settings: {type(e).__name__}: {e}")
    sym = _match(a.symbol, cfg.symbols)
    if sym is None:
        return _refuse(a, f"{a.symbol!r} is not one of the bot's symbols {list(cfg.symbols)}")
    extra = {}
    if a.bot:
        try:
            price, stop, atr, signal = bot_price_and_stop(sym, cfg)
        except Exception as e:  # noqa: BLE001
            return _refuse(a, f"could not get the bot's live price/stop: {type(e).__name__}: {e}")
        extra = {"source": "bot (live Binance ticker, ensemble ATR at the last closed candle)", "atr_pct": atr,
                 "bot_signal_now": signal}
    else:
        price, stop = a.price, a.stop
    b = size(sym, price, stop, load_context(_run_dir(cfg), cfg.market), cfg)
    from datetime import datetime, timezone
    out = _clean({**asdict(b), **extra, "mode": a.mode, "placed": False,
                  "created_utc": datetime.now(timezone.utc).isoformat(timespec="seconds")})
    ok = b.qty > 0 and b.risk_verdict["decision"] == "PASS"
    p = _proposal_path(a.mode)
    if a.write and ok:
        p.parent.mkdir(exist_ok=True)
        tmp = p.with_suffix(".tmp")
        tmp.write_text(json.dumps(out, indent=2), encoding="utf-8")
        tmp.replace(p)  # atomic: a reader never sees half a proposal
        out["written"] = str(p)
    elif a.write and p.exists():
        p.unlink()  # a refused run must not leave an older PASS proposal looking current
        out["removed_stale_proposal"] = str(p)
    text = _fmt(b)
    if extra.get("bot_signal_now"):
        text += f"\n  bot signal now: {extra['bot_signal_now']} (the size is what it WOULD buy if it fired)"
    if "written" in out:
        text += f"\n  written: {out['written']}"
    if "removed_stale_proposal" in out:
        text += f"\n  removed old proposal: {out['removed_stale_proposal']}"
    print(json.dumps(out, indent=2) if a.json else text)
    return EXIT_PASS if ok else EXIT_BLOCK


if __name__ == "__main__":
    sys.exit(main())
