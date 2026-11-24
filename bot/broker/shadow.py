"""Shadow broker: real-time public market data, real production risk checks, NO real orders.

It is a PaperBroker that additionally records every order *intention* (what the engine wanted to send)
with the reference price, the modelled fill, and how late (wall-clock) the intention came after the
candle closed. It contains no network code and takes no credentials, so it cannot place a real order.
Limitation: fills are modelled from the last public price plus configured slippage, not from a real
venue order book (no spot venue is integrated yet), so "fill quality" here is a model, not a measurement.
"""

from __future__ import annotations

import csv
from pathlib import Path

import pandas as pd

from ..config import Settings
from .base import Feed, Fill
from .paper import PaperBroker

COLUMNS = ["ts", "symbol", "side", "contracts", "reason", "ref_price", "modeled_fill_price",
           "modeled_slippage_pct", "latency_s_after_candle_close", "order_id"]


class ShadowBroker(PaperBroker):
    def __init__(self, feed: Feed, cfg: Settings, path: Path | str, intents_path: Path | str):
        if cfg.mode != "shadow":
            raise RuntimeError("ShadowBroker only runs with mode='shadow'")
        super().__init__(feed, cfg, path)
        self.intents_path = Path(intents_path)
        self.intents_path.parent.mkdir(parents=True, exist_ok=True)

    def _record(self, symbol: str, side: str, contracts: float, reason: str, ref: float, fill: Fill | None) -> None:
        now = self.feed.now()
        tf = pd.Timedelta(minutes=self.cfg.tf_minutes)
        latency = (now - now.floor(tf)).total_seconds()
        px = fill.price if fill else ""
        slip = ((fill.price / ref - 1) * (1 if side == "buy" else -1) * 100) if fill and ref else ""
        new = not self.intents_path.exists()
        with self.intents_path.open("a", newline="", encoding="utf-8") as fh:
            w = csv.writer(fh)
            if new:
                w.writerow(COLUMNS)
            w.writerow([now.isoformat(), symbol, side, contracts, reason, ref, px,
                        slip if slip == "" else round(slip, 5), round(latency, 1), fill.order_id if fill else "rejected"])

    def market_order(self, symbol, side, contracts, reduce_only=False, reason="") -> Fill | None:
        ref = self.feed.last_price(symbol)
        fill = super().market_order(symbol, side, contracts, reduce_only, reason)
        self._record(symbol, side, contracts, reason or "order", ref, fill)
        return fill

    def place_stop(self, symbol, side, contracts, stop_price) -> str:
        oid = super().place_stop(symbol, side, contracts, stop_price)
        self._record(symbol, side, contracts, f"stop@{stop_price:.6g}", self.feed.last_price(symbol), None)
        return oid
