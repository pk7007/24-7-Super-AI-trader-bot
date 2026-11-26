"""crypto-risk: PASS/BLOCK verdict for a proposed order, against the same policy the bot enforces.

Read-only. It never places, changes or cancels an order and never writes bot state. Every check that
cannot run (missing or corrupt state, bad input) BLOCKS: the verdict fails closed, never open.

    python -m bot.riskcheck --symbol BTC --side buy --qty 0.0002 --price 95000 --stop 93000
    python -m bot.riskcheck ... --mode shadow --json
    python -m bot.riskcheck --symbol BTC --side buy --price 95000 --stop 93000   # no --qty: just sizes it

Exit codes: 0 = PASS, 20 = BLOCK, 2 = usage error.
"""

from __future__ import annotations

import argparse
import json
import math
import sqlite3
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path

from .config import Settings
from .risk import round_trip_cost_pct  # same cost model the bot sizes with

EXIT_PASS, EXIT_BLOCK = 0, 20
TOL = 1e-9  # float tolerance on "<=" limits; never loosens a limit by a meaningful amount


@dataclass
class Order:
    symbol: str
    side: str  # "buy" or "sell"
    qty: float | None  # base units (coins); None = size it for me
    price: float
    stop: float | None


@dataclass
class Context:
    """What the bot's own state says right now."""
    equity: float
    positions: dict[str, dict]  # symbol -> {"side", "contracts" (bot units), "coins", "entry", "stop"}
    halted: dict[str, bool]  # {"daily": bool, "weekly": bool, "monthly": bool}
    errors: list[str] = field(default_factory=list)  # anything that could not be read -> BLOCK


@dataclass
class Verdict:
    decision: str  # "PASS" | "BLOCK"
    reasons: list[str]  # every failed check, in plain words (empty on PASS)
    checks: list[dict]  # every check run: {"name", "ok", "detail"}
    numbers: dict  # risk in money and % of equity, notional, max qty and which limit decided it


def _finite_pos(x) -> bool:
    return isinstance(x, (int, float)) and math.isfinite(x) and x > 0


def _match(symbol: str, cfg_symbols) -> str | None:
    """Accept 'BTC', 'BTC/USDT' or 'BTC/USD:USD'; return the bot's own symbol or None.
    A different quote currency (BTC/INR, BTC/ETH) is a different market and does not match."""
    s_up = (symbol or "").upper().strip()
    base, _, rest = s_up.partition("/")
    quote, _, settle = rest.partition(":")
    usd = ("", "USD", "USDT", "USDC")
    if quote not in usd or settle not in usd or ":" in base or not base:
        return None
    for s in cfg_symbols:
        if s.split("/")[0].upper() == base:
            return s
    return None


def evaluate(order: Order, ctx: Context, cfg: Settings) -> Verdict:
    checks: list[dict] = []

    def check(name: str, ok: bool, detail: str) -> bool:
        checks.append({"name": name, "ok": bool(ok), "detail": detail})
        return ok

    nums: dict = {"equity": ctx.equity}

    # 0. the bot's own state must be readable (fail closed)
    check("state_readable", not ctx.errors, "; ".join(ctx.errors) or "state.db and paper exchange read")

    # 1. inputs
    side = (order.side or "").lower()
    ok_side = check("side_valid", side in ("buy", "sell"), f"side={order.side!r}")
    ok_price = check("price_valid", _finite_pos(order.price), f"price={order.price!r}")
    if order.qty is not None:
        check("qty_valid", _finite_pos(order.qty), f"qty={order.qty!r}")
    sym = _match(order.symbol, cfg.symbols)
    check("symbol_traded", sym is not None, f"{order.symbol!r} vs bot symbols {list(cfg.symbols)}")

    held = ctx.positions.get(sym) if sym else None
    is_exit = ok_side and held is not None and (
        (held["side"] > 0 and side == "sell") or (held["side"] < 0 and side == "buy"))

    if is_exit:
        # Reducing an existing position always lowers risk; allowed even when halted (the kill-switch
        # itself flattens). It must still name a size, and not flip the position.
        if check("exit_qty_given", order.qty is not None, "an exit must state its quantity"):
            if _finite_pos(order.qty):
                check("exit_not_larger_than_position", order.qty <= held["coins"] * (1 + TOL),
                      f"qty {order.qty} coins vs held {held['coins']} coins")
        nums["kind"] = "exit"
        return _finish(checks, nums)

    nums["kind"] = "entry"
    # 2. direction policy
    long_ = side == "buy"
    if ok_side and not long_:
        check("shorting_allowed", cfg.allow_short,
              "spot profile is long-only: a sell with no position to close is a short")

    # 3. kill-switches
    tripped = [k for k, v in ctx.halted.items() if v]
    check("kill_switch_clear", not tripped,
          ("tripped: " + ", ".join(tripped) + " -> no new entries until the next period") if tripped else "none tripped")

    # 4. position count / duplicates
    if sym is not None:
        check("not_already_held", held is None, f"{sym} already open" if held else "not held")
    check("max_positions", len(ctx.positions) < cfg.max_positions,
          f"{len(ctx.positions)} open, limit {cfg.max_positions}")

    # 5. stop (RULE 2): required, on the protective side
    if not check("stop_given", order.stop is not None and _finite_pos(order.stop), f"stop={order.stop!r}"):
        return _finish(checks, nums)
    if not ok_price or not ok_side:
        return _finish(checks, nums)
    stop_dist = (order.price - order.stop) if long_ else (order.stop - order.price)
    if not check("stop_on_protective_side", stop_dist > 0,
                 f"{'long' if long_ else 'short'} entry {order.price} with stop {order.stop}"):
        return _finish(checks, nums)

    # 6. size: risk budget, leverage, minimum order
    eq = ctx.equity
    if not check("equity_positive", _finite_pos(eq), f"equity={eq!r}"):
        return _finish(checks, nums)
    cost = round_trip_cost_pct(cfg)
    per_unit_loss = stop_dist + order.price * cost  # worst case at the stop, including costs
    budget = eq * cfg.risk_per_trade
    max_by_risk = budget / per_unit_loss
    max_by_lev = eq * cfg.max_leverage / order.price
    max_qty = min(max_by_risk, max_by_lev)
    binding = "risk_per_trade" if max_by_risk <= max_by_lev else "max_leverage"
    nums.update({"risk_budget": round(budget, 6), "stop_distance_pct": round(stop_dist / order.price * 100, 4),
                 "cost_pct_round_trip": round(cost * 100, 4), "max_qty": max_qty,
                 "max_qty_by_risk": max_by_risk, "max_qty_by_leverage": max_by_lev, "binding_limit": binding})
    qty = order.qty if order.qty is not None else max_qty
    if order.qty is None:
        nums["sized_for_you"] = True
    if not _finite_pos(qty):
        return _finish(checks, nums)
    risk = qty * per_unit_loss
    notional = qty * order.price
    nums.update({"qty": qty, "risk": round(risk, 6), "risk_pct_equity": round(risk / eq * 100, 4),
                 "notional": round(notional, 6), "notional_inr": round(notional * cfg.usdt_inr, 2),
                 "leverage": round(notional / eq, 4)})
    check("risk_per_trade", risk <= budget * (1 + TOL),
          f"loss at stop incl. costs {risk:.4f} = {risk / eq:.3%} of equity, limit {cfg.risk_per_trade:.3%}")
    check("max_leverage", notional <= eq * cfg.max_leverage * (1 + TOL),
          f"notional {notional:.4f} = {notional / eq:.2f}x equity, limit {cfg.max_leverage:g}x")
    open_notional = sum(abs(p["coins"]) * p["entry"] for p in ctx.positions.values())
    nums["open_notional"] = round(open_notional, 6)
    check("total_exposure", notional + open_notional <= eq * cfg.max_leverage * (1 + TOL),
          f"this order {notional:.4f} + open positions {open_notional:.4f} vs {cfg.max_leverage:g}x equity "
          f"{eq * cfg.max_leverage:.4f} (spot cannot spend the same cash twice)")
    check("min_order", notional * cfg.usdt_inr >= cfg.min_order_inr,
          f"Rs {notional * cfg.usdt_inr:.0f} vs minimum Rs {cfg.min_order_inr:.0f}")
    return _finish(checks, nums)


def _finish(checks: list[dict], nums: dict) -> Verdict:
    failed = [f"{c['name']}: {c['detail']}" for c in checks if not c["ok"]]
    return Verdict("BLOCK" if failed else "PASS", failed, checks, nums)


# ------------------------------------------------------------------ reading the bot's state (read-only)
def _run_dir(cfg: Settings) -> Path:
    return cfg.run_dir


def coin_units(symbol: str, market: str = "spot") -> float:
    """Coins per bot unit. The engine stores ``contracts`` as a count of lot steps (spot) or exchange
    contracts (perp), never as coins (engine._scan -> to_contracts; paper broker multiplies by it)."""
    from .feeds import DEFAULT_CONTRACT_SIZE, SPOT_STEP
    table = SPOT_STEP if market == "spot" else DEFAULT_CONTRACT_SIZE
    if symbol not in table:
        raise KeyError(f"no unit size for {symbol}")
    return float(table[symbol])


def load_context(run_dir: Path, market: str = "spot") -> Context:
    """Equity is CONSERVATIVE: cash plus each open position's P&L if its stop is hit. That is never above the
    bot's own equity (cash + unrealised P&L) while a position is above its stop, so sizing on it can only
    risk LESS than the policy share of the bot's true equity."""
    errors: list[str] = []
    equity, positions = float("nan"), {}
    halted = {"daily": False, "weekly": False, "monthly": False}

    px = run_dir / "paper_exchange.json"
    try:
        s = json.loads(px.read_text(encoding="utf-8"))
        equity = float(s["cash"])  # + each open position at its stop, below
    except FileNotFoundError:
        errors.append(f"{px.name} missing (bot never started in this mode?)")
    except Exception as e:  # noqa: BLE001 - any unreadable state blocks
        errors.append(f"{px.name} unreadable: {type(e).__name__}")

    db = run_dir / "state.db"
    if not db.exists():
        errors.append("state.db missing")
    else:
        try:
            con = sqlite3.connect(f"file:{db.as_posix()}?mode=ro", uri=True, timeout=5)
            try:
                for sym, side, n, entry, stop in con.execute(
                        "SELECT symbol, side, contracts, entry, stop FROM positions"):
                    if side not in (1, -1):
                        errors.append(f"position {sym} has invalid side {side!r}")
                    try:
                        coins = float(n) * coin_units(sym, market)
                    except KeyError as e:
                        errors.append(str(e))
                        coins = float("nan")
                    positions[sym] = {"side": side, "contracts": float(n), "coins": coins,
                                      "entry": float(entry), "stop": float(stop)}
                kv = dict(con.execute("SELECT key, value FROM kv WHERE key IN "
                                      "('ks_halted','ksw_halted','ksm_halted')").fetchall())
            finally:
                con.close()
            # A missing key means the switch never tripped (the engine reads it the same way). Any value
            # other than "0"/"1" is corruption and blocks; it is never read as "clear".
            for name, key in (("daily", "ks_halted"), ("weekly", "ksw_halted"), ("monthly", "ksm_halted")):
                val = kv.get(key, "0")
                if val not in ("0", "1"):
                    errors.append(f"kill-switch {key}={val!r} unreadable")
                halted[name] = val != "0"
        except Exception as e:  # noqa: BLE001
            errors.append(f"state.db unreadable: {type(e).__name__}: {e}")
    for p in positions.values():  # worst case for each open position: its stop fills
        equity += p["side"] * (p["stop"] - p["entry"]) * p["coins"]
    if positions and not math.isfinite(equity):
        errors.append("equity incl. open positions at their stops is not a number")
    return Context(equity, positions, halted, errors)


def _fmt(v: Verdict, order: Order) -> str:
    n = v.numbers
    lines = [f"{v.decision}: {order.side} {order.symbol} qty {n.get('qty', order.qty)} @ {order.price} stop {order.stop}"]
    if v.reasons:
        lines += ["  blocked by:"] + [f"   - {r}" for r in v.reasons]
    if "max_qty" in n:
        lines.append(f"  max qty allowed {n['max_qty']:.8f} (decided by {n['binding_limit']}); "
                     f"risk budget {n['risk_budget']:.4f} of equity {n['equity']:.2f}")
    if "risk" in n:
        lines.append(f"  this order: loss at stop {n['risk']:.4f} ({n['risk_pct_equity']:.3f}% of equity), "
                     f"notional {n['notional']:.4f} (Rs {n['notional_inr']:.0f}), {n['leverage']:.2f}x")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m bot.riskcheck", description=__doc__.split("\n\n")[0])
    ap.add_argument("--symbol", required=True)
    ap.add_argument("--side", required=True, choices=["buy", "sell"])
    ap.add_argument("--qty", type=float, help="base units (coins); omit to get the max allowed size")
    ap.add_argument("--price", type=float, required=True, help="expected entry price")
    ap.add_argument("--stop", type=float, help="stop-loss price (required for entries)")
    ap.add_argument("--mode", default="paper", choices=["paper", "shadow"])
    ap.add_argument("--equity", type=float, help="override equity (what-if); state is still read for limits")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)

    import os
    os.environ.setdefault("STRATEGY", "ensemble")
    os.environ.setdefault("MARKET", "spot")
    os.environ["BOT_MODE"] = a.mode
    order = Order(a.symbol, a.side, a.qty, a.price, a.stop)
    try:
        cfg = Settings.from_env()  # same policy-enforced settings the bot runs with
    except Exception as e:  # noqa: BLE001 - a bad setting must BLOCK, not crash with another exit code
        v = Verdict("BLOCK", [f"settings: {type(e).__name__}: {e}"], [], {})
    else:
        ctx = load_context(_run_dir(cfg), cfg.market)
        override = None
        if a.equity is not None:
            # what-if may only make limits STRICTER: never above the account's real equity
            if not (_finite_pos(a.equity) and _finite_pos(ctx.equity) and a.equity <= ctx.equity):
                ctx.errors.append(f"--equity {a.equity} refused: must be > 0 and <= account equity {ctx.equity}")
            else:
                override, ctx.equity = a.equity, a.equity
        v = evaluate(order, ctx, cfg)
        if override is not None:
            v.numbers["equity_override"] = override
    print(json.dumps(asdict(v), indent=2) if a.json else _fmt(v, order))
    return EXIT_PASS if v.decision == "PASS" else EXIT_BLOCK


if __name__ == "__main__":
    sys.exit(main())
