"""Live Delta Exchange India broker via ccxt.

STATUS: UNTESTED against the real API (no credentials were available when this was written).
Run it against the testnet (DELTA_TESTNET=1) and verify every method before risking money.
ccxt's unified ``stopLossPrice`` is NOT supported for Delta, so the stop is sent with Delta's
native fields (``stop_order_type`` / ``stop_price`` / ``reduce_only``), which ccxt forwards raw.
"""

from __future__ import annotations

import os

import ccxt
import pandas as pd

from ..config import Settings
from .base import Broker, ExPosition, Fill


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
        key, secret = os.environ.get("DELTA_API_KEY"), os.environ.get("DELTA_API_SECRET")
        if not key or not secret:
            raise LiveTradingNotAllowed("DELTA_API_KEY / DELTA_API_SECRET missing from .env")
        self.cfg, self.asset = cfg, balance_asset
        self.ex = ccxt.delta({"apiKey": key, "secret": secret, "enableRateLimit": True, "timeout": 20000})
        self.ex.urls["api"] = {"public": cfg.api_base, "private": cfg.api_base}
        self.ex.load_markets()
        self._seen: set[str] = set()
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
        self._seen.add(str(o["id"]))
        px = float(o.get("average") or o.get("price") or 0)
        fee = float((o.get("fee") or {}).get("cost") or 0)
        return Fill(pd.Timestamp.now(tz="UTC").isoformat(), symbol, side, float(o.get("filled") or contracts),
                    px, fee, 0.0, reason, str(o["id"]))

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
        out: list[Fill] = []
        for t in self.ex.fetch_my_trades(since=self._since_ms):
            tid = str(t.get("order") or t["id"])
            if tid in self._seen:
                continue
            self._seen.add(tid)
            fee = float((t.get("fee") or {}).get("cost") or 0)
            out.append(Fill(pd.Timestamp(t["timestamp"], unit="ms", tz="UTC").isoformat(), t["symbol"],
                            t["side"], float(t["amount"]), float(t["price"]), fee, 0.0, "stop", tid))
        return out

    def tick(self) -> None:  # exchange evaluates stops itself
        return None
