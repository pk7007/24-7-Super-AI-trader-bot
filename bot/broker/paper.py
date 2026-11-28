"""Simulated exchange. State is persisted to JSON after every mutation so that, like a real
exchange, positions and resting stop orders SURVIVE a bot restart (needed to test RULE 3)."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pandas as pd

from ..config import Settings
from .base import Broker, ExPosition, Feed, Fill


class PaperBroker(Broker):
    def __init__(self, feed: Feed, cfg: Settings, path: Path | str):
        self.feed, self.cfg, self.path = feed, cfg, Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if self.path.exists():
            self.s = json.loads(self.path.read_text())
        else:
            self.s = {"cash": cfg.start_equity, "positions": {}, "stops": {}, "seq": 0, "fills": []}
            self._save()

    # ------------------------------------------------------------ persistence
    def _save(self) -> None:
        """Write a temp file, force it to disk, then swap it in. Without the fsync a power cut can leave the
        rename on disk but not the data (2026-11-27: the account became 68 zero bytes and the bot could not start)."""
        tmp = self.path.with_suffix(".tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(json.dumps(self.s))
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, self.path)

    def _next_id(self) -> str:
        self.s["seq"] += 1
        return f"P{self.s['seq']}"

    # ----------------------------------------------------------------- queries
    def equity(self) -> float:
        eq = self.s["cash"]
        for sym, p in self.s["positions"].items():
            cs = self.feed.contract_size(sym)
            eq += p["side"] * (self.feed.last_price(sym) - p["entry"]) * p["contracts"] * cs
        return eq

    def positions(self) -> dict[str, ExPosition]:
        return {s: ExPosition(s, p["side"], p["contracts"], p["entry"])
                for s, p in self.s["positions"].items()}

    def open_stop_ids(self, symbol: str) -> set[str]:
        return {i for i, o in self.s["stops"].items() if o["symbol"] == symbol}

    # ------------------------------------------------------------------ orders
    def _apply(self, symbol: str, side: str, contracts: float, px: float, taker: bool,
               reason: str, reduce_only: bool) -> Fill | None:
        cs = self.feed.contract_size(symbol)
        signed = contracts if side == "buy" else -contracts
        pos = self.s["positions"].get(symbol)
        if reduce_only:
            if pos is None or pos["side"] * signed > 0:
                return None  # nothing to reduce, or would increase
            contracts = min(contracts, pos["contracts"])
            signed = contracts if side == "buy" else -contracts
        fee_rate = (self.cfg.taker_fee if taker else self.cfg.maker_fee) * self.cfg.gst
        fee = contracts * cs * px * fee_rate
        realized = 0.0
        if pos is None:
            self.s["positions"][symbol] = {"side": 1 if signed > 0 else -1,
                                           "contracts": contracts, "entry": px}
        else:
            cur = pos["side"] * pos["contracts"]
            new = cur + signed
            if cur * signed > 0:  # adding
                tot = pos["contracts"] + contracts
                pos["entry"] = (pos["entry"] * pos["contracts"] + px * contracts) / tot
                pos["contracts"] = tot
            else:  # reducing / flipping
                closed = min(abs(signed), pos["contracts"])
                realized = closed * cs * (px - pos["entry"]) * pos["side"]
                if abs(new) < 1e-12:
                    del self.s["positions"][symbol]
                elif new * cur > 0:
                    pos["contracts"] = abs(new)
                else:
                    self.s["positions"][symbol] = {"side": 1 if new > 0 else -1,
                                                   "contracts": abs(new), "entry": px}
        self.s["cash"] += realized - fee
        if symbol not in self.s["positions"]:  # reduce-only stops die with the position
            for i in [i for i, o in self.s["stops"].items() if o["symbol"] == symbol]:
                del self.s["stops"][i]
        oid = self._next_id()
        fill = Fill(self.feed.now().isoformat(), symbol, side, contracts, px, fee, realized,
                    reason, oid, fill_id=f"paper:{oid}")
        return fill

    def market_order(self, symbol, side, contracts, reduce_only=False, reason="") -> Fill | None:
        last = self.feed.last_price(symbol)
        px = last * (1 + self.cfg.slippage) if side == "buy" else last * (1 - self.cfg.slippage)
        fill = self._apply(symbol, side, contracts, px, True, reason, reduce_only)
        self._save()
        return fill

    def place_stop(self, symbol, side, contracts, stop_price) -> str:
        oid = self._next_id()
        self.s["stops"][oid] = {"symbol": symbol, "side": side, "contracts": contracts,
                                "stop": stop_price, "since": self.feed.now().isoformat()}
        self._save()
        return oid

    def cancel_order(self, symbol, order_id) -> None:
        self.s["stops"].pop(order_id, None)
        self._save()

    # ------------------------------------------------------------- stop engine
    def tick(self) -> None:
        now = self.feed.now()
        for oid, o in list(self.s["stops"].items()):
            sym = o["symbol"]
            if sym not in self.s["positions"]:
                del self.s["stops"][oid]
                continue
            hit = False
            for high, low in self.feed.range_since(sym, pd.Timestamp(o["since"])):
                if (o["side"] == "sell" and low <= o["stop"]) or (o["side"] == "buy" and high >= o["stop"]):
                    hit = True
                    break
            if hit:
                slip = self.cfg.stop_slippage
                px = o["stop"] * (1 - slip) if o["side"] == "sell" else o["stop"] * (1 + slip)
                del self.s["stops"][oid]
                fill = self._apply(sym, o["side"], o["contracts"], px, True, "stop", True)
                if fill:
                    self.s["fills"].append(fill.__dict__)
            else:
                o["since"] = now.isoformat()
        self._save()

    def drain_fills(self) -> list[Fill]:
        out = self.pending_fills()
        for f in out:
            self.ack_fill(f)
        return out

    def pending_fills(self) -> list[Fill]:
        return [Fill(**{**f, "fill_id": f.get("fill_id") or f"paper:{f['order_id']}"}) for f in self.s["fills"]]

    def ack_fill(self, fill: Fill) -> None:
        self.s["fills"] = [f for f in self.s["fills"]
                           if (f.get("fill_id") or f"paper:{f['order_id']}") != fill.fill_id]
        self._save()
