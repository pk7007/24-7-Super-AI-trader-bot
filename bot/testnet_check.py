"""Testnet verification checklist for DeltaBroker (python -m bot.main testnet-check).

Refuses to run unless DELTA_TESTNET=1 AND BOT_MODE=live AND I_UNDERSTAND_LIVE_RISK=yes, so it can
never touch real money by accident. Trades ONE contract of BTC/USD:USD, then cleans up in ``finally``.
Every step prints PASS/FAIL with the evidence you need to fix the broker if something is wrong.
"""

from __future__ import annotations

import os
import tempfile
import time
from dataclasses import replace
from pathlib import Path

import pandas as pd

from .broker.delta import DeltaBroker, require_live_consent
from .config import Settings
from .engine import Engine
from .feeds import LiveFeed
from .ledger import Ledger
from .state import Position, State

SYMBOL = "BTC/USD:USD"


class TestnetOnly(RuntimeError):
    __test__ = False  # not a pytest class


def guard(cfg: Settings) -> None:
    if os.environ.get("DELTA_TESTNET", "1") != "1" or not cfg.testnet:
        raise TestnetOnly("refusing: DELTA_TESTNET must be 1 for the testnet checklist")
    require_live_consent()


class Checklist:
    def __init__(self):
        self.results: list[tuple[str, bool, str]] = []

    def check(self, name: str, ok: bool, evidence: str = "") -> bool:
        self.results.append((name, bool(ok), evidence))
        print(f"[{'PASS' if ok else 'FAIL'}] {name}  {evidence}")
        return bool(ok)

    @property
    def all_ok(self) -> bool:
        return bool(self.results) and all(ok for _, ok, _ in self.results)


def run(cfg: Settings, asset: str = "USD") -> bool:
    guard(cfg)
    cfg = replace(cfg, mode="live", symbols=(SYMBOL,))
    cl = Checklist()
    broker = DeltaBroker(cfg, balance_asset=asset)
    feed = LiveFeed(cfg)
    tmp = Path(tempfile.mkdtemp(prefix="testnet_check_"))
    state = State(tmp / "state.db")
    ledger = Ledger(tmp / "ledger.csv", state)
    try:
        # 1. account + preconditions ------------------------------------------------
        eq = broker.equity()
        cl.check("fetch equity", eq > 0, f"equity={eq} {asset} (use --asset if this fails)")
        cl.check("no pre-existing positions", not broker.positions(), str(broker.positions()))
        cl.check("no pre-existing resting orders", not broker.open_stop_ids(SYMBOL), "")

        # 2. entry + exchange-side stop ----------------------------------------------
        fill = broker.market_order(SYMBOL, "buy", 1, reason="entry")
        cl.check("market buy returns a fill with price", bool(fill and fill.price > 0), str(fill))
        time.sleep(1)
        pos = broker.positions().get(SYMBOL)
        cl.check("position visible on exchange", bool(pos and pos.side == 1 and pos.contracts == 1), str(pos))
        stop_px = fill.price * 0.97
        sid = broker.place_stop(SYMBOL, "sell", 1, stop_px)
        time.sleep(1)
        cl.check("stop order accepted and resting", sid in broker.open_stop_ids(SYMBOL), f"id={sid} @ {stop_px:.1f}")
        state.upsert_position(Position(SYMBOL, 1, 1, fill.price, stop_px, sid,
                                       pd.Timestamp.now(tz="UTC").isoformat()))
        ledger.record(fill)

        # 3. restart recovery: DB and exchange agree -> reconcile changes nothing ------
        notes = Engine(cfg, broker, feed, None, state, ledger, notify=print).reconcile()
        cl.check("reconcile leaves a healthy position and stop alone", not notes, str(notes))

        # 4. stop vanished -> reconcile restores it ---------------------------------
        broker.cancel_order(SYMBOL, sid)
        time.sleep(1)
        cl.check("stop cancelled", sid not in broker.open_stop_ids(SYMBOL), "")
        notes = Engine(cfg, broker, feed, None, state, ledger, notify=print).reconcile()
        new_sid = state.positions()[SYMBOL].stop_id
        cl.check("reconcile re-places a missing stop", new_sid != sid and new_sid in broker.open_stop_ids(SYMBOL),
                 str(notes))

        # 5. DB lost -> unknown exchange position is flattened ----------------------
        state2 = State(tmp / "lost.db")
        notes = Engine(cfg, broker, feed, None, state2, Ledger(tmp / "l2.csv", state2), notify=print).reconcile()
        time.sleep(1)
        cl.check("orphan position flattened and its stop cancelled",
                 not broker.positions() and not broker.open_stop_ids(SYMBOL), str(notes))

        # 6. fills ------------------------------------------------------------------
        fills = broker.drain_fills()
        cl.check("drain_fills runs and returns Fill objects", all(hasattr(f, "price") for f in fills),
                 f"n={len(fills)}")
    finally:
        try:  # always leave the testnet account flat
            for oid in broker.open_stop_ids(SYMBOL):
                broker.cancel_order(SYMBOL, oid)
            pos = broker.positions().get(SYMBOL)
            if pos:
                broker.market_order(SYMBOL, "sell" if pos.side > 0 else "buy", pos.contracts,
                                    reduce_only=True, reason="cleanup")
        except Exception as exc:  # noqa: BLE001
            print(f"CLEANUP FAILED - check the testnet account by hand: {exc}")
    print("\nALL PASSED" if cl.all_ok else "\nSOME CHECKS FAILED - do not go live")
    return cl.all_ok
