"""Live Delta Exchange India broker via ccxt.

STATUS: a testnet check was recorded on 2026-11-27; the later full-audit changes have only
offline verification. Startup trade-history recovery and pagination remain incomplete.
Run the updated adapter against testnet before considering any live-money review.
ccxt's unified ``stopLossPrice`` is NOT supported for Delta, so the stop is sent with Delta's
native fields (``stop_order_type`` / ``stop_price`` / ``reduce_only``), which ccxt forwards raw.
"""

from __future__ import annotations

import os
import math

import ccxt
import pandas as pd

from ..config import Settings
from .base import Broker, ExPosition, Fill

# Change when execution/accounting semantics change; prior testnet runs are historical.
EXECUTION_VERSION = 2


class LiveTradingNotAllowed(RuntimeError):
    pass


def require_live_consent() -> None:
    if os.environ.get("BOT_MODE", "").lower() != "live" or os.environ.get("I_UNDERSTAND_LIVE_RISK") != "yes":
        raise LiveTradingNotAllowed(
            "Live trading needs BOT_MODE=live and I_UNDERSTAND_LIVE_RISK=yes in .env"
        )


class DeltaBroker(Broker):
    def __init__(self, cfg: Settings, balance_asset: str = "USD"):
        require_live_consent()
        if cfg.market != "perp":
            raise LiveTradingNotAllowed("DeltaBroker supports perpetual futures only; no spot execution adapter exists")
        key, secret = os.environ.get("DELTA_API_KEY"), os.environ.get("DELTA_API_SECRET")
        if not key or not secret:
            raise LiveTradingNotAllowed("DELTA_API_KEY / DELTA_API_SECRET missing from .env")
        self.cfg, self.asset = cfg, balance_asset
        self.ex = ccxt.delta({"apiKey": key, "secret": secret, "enableRateLimit": True, "timeout": 20000})
        self.ex.urls["api"] = {"public": cfg.api_base, "private": cfg.api_base}
        self.ex.load_markets()
        self._seen: set[str] = set()
        self._seen_trades: set[str] = set()
        self._since_ms = int(pd.Timestamp.now(tz="UTC").timestamp() * 1000)

    def _cs(self, symbol: str) -> float:
        return float(self.ex.market(symbol)["contractSize"])

    def equity(self) -> float:
        bal = self.ex.fetch_balance()
        total = bal.get("total", {}).get(self.asset)
        if total is None:
            raise RuntimeError(f"balance asset {self.asset!r} not found; set it explicitly")
        return float(total)

    def positions(self) -> dict[str, ExPosition]:
        out: dict[str, ExPosition] = {}
        for p in self.ex.fetch_positions(list(self.cfg.symbols)):
            n = float(p.get("contracts") or 0)
            if n:
                out[p["symbol"]] = ExPosition(
                    p["symbol"], 1 if p["side"] == "long" else -1, n, float(p.get("entryPrice") or 0))
        return out

    def market_order(self, symbol, side, contracts, reduce_only=False, reason="") -> Fill | None:
        params = {"reduceOnly": True} if reduce_only else {}
        o = self.ex.create_order(symbol, "market", side, contracts, None, params)
        qty = float(o.get("filled") or 0)
        px = float(o.get("average") or o.get("price") or 0)
        if (o.get("status") not in ("closed", "canceled") or not math.isfinite(qty) or qty <= 0
                or qty > contracts or not math.isfinite(px) or px <= 0):
            raise RuntimeError("market order has no confirmed terminal execution; account reconciliation required")
        self._seen.add(f"{symbol}:{o['id']}")
        fee = float((o.get("fee") or {}).get("cost") or 0)
        return Fill(pd.Timestamp.now(tz="UTC").isoformat(), symbol, side, qty,
                    px, fee, 0.0, reason, str(o["id"]), fill_id=f"delta-order:{symbol}:{o['id']}")

    def place_stop(self, symbol, side, contracts, stop_price) -> str:
        px = self.ex.price_to_precision(symbol, stop_price)
        o = self.ex.create_order(symbol, "market", side, contracts, None, {
            "reduceOnly": True,
            "stop_order_type": "stop_loss_order",
            "stop_price": px,
            "stop_trigger_method": "last_traded_price",
        })
        return str(o["id"])

    def cancel_order(self, symbol, order_id) -> None:
        try:
            self.ex.cancel_order(order_id, symbol)
        except ccxt.OrderNotFound:
            pass

    def open_stop_ids(self, symbol: str) -> set[str]:
        return {str(o["id"]) for o in self.ex.fetch_open_orders(symbol)}

    def drain_fills(self) -> list[Fill]:
        out = self.pending_fills()
        for f in out:
            self.ack_fill(f)
        return out

    def pending_fills(self) -> list[Fill]:
        out: list[Fill] = []
        for t in self.ex.fetch_my_trades(since=self._since_ms):
            tid = str(t["id"])
            identity = f"{t['symbol']}:{tid}"
            if f"{t['symbol']}:{t.get('order')}" in self._seen or identity in self._seen_trades:
                continue
            fee = float((t.get("fee") or {}).get("cost") or 0)
            out.append(Fill(pd.Timestamp(t["timestamp"], unit="ms", tz="UTC").isoformat(), t["symbol"],
                            t["side"], float(t["amount"]), float(t["price"]), fee, 0.0, "stop",
                            str(t.get("order") or tid), fill_id=f"delta-trade:{identity}"))
        return out

    def ack_fill(self, fill: Fill) -> None:
        self._seen_trades.add(fill.fill_id.removeprefix("delta-trade:"))

    def tick(self) -> None:  # exchange evaluates stops itself
        return None
