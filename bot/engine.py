"""Trading engine shared by paper, replay and live. Enforces the non-negotiable rules:

  RULE 2  every entry gets an exchange-side stop immediately; if it cannot be placed the
          position is flattened on the spot.
  RULE 3  ``reconcile()`` must run (and finish) before any order; ``step`` refuses otherwise.
  RULE 4  daily drawdown >= limit flattens everything and blocks new entries until next UTC day.
  RULE 5  every fill goes through the ledger.
"""

from __future__ import annotations

import logging
import math
from typing import Callable

import pandas as pd

from .broker.base import Broker, Feed, Fill
from .config import Settings
from .features import build_features
from .ledger import Ledger
from .model import SignalModel
from .portfolio_risk import check_entry
from .risk import DailyKillSwitch, position_units, stop_price, to_contracts
from .state import Position, State
from .strategy import decide, should_exit_on_flip

log = logging.getLogger("engine")

ORPHAN_STOP_PCT = 0.02  # protective stop for adopted (unknown) positions


class Engine:
    def __init__(self, cfg: Settings, broker: Broker, feed: Feed, model: SignalModel,
                 state: State, ledger: Ledger, notify: Callable[[str], None] = lambda m: None,
                 venue_price: Callable[[str], float] | None = None):
        """``venue_price(symbol)`` = price on the EXECUTION venue (Delta). When given, entries are
        skipped if it deviates more than ``cfg.max_venue_deviation`` from the signal feed, or if it
        cannot be fetched (fail-safe)."""
        self.venue_price = venue_price
        self.cfg, self.broker, self.feed, self.model = cfg, broker, feed, model
        self.state, self.ledger, self.notify = state, ledger, notify
        self.tf = pd.Timedelta(minutes=cfg.tf_minutes)
        self.ks = DailyKillSwitch(cfg.daily_loss_limit)
        # Same mechanism over longer windows (P1 roadmap): halts entries + flattens until the next period.
        self.ks_week = DailyKillSwitch(cfg.weekly_loss_limit)
        self.ks_month = DailyKillSwitch(cfg.monthly_loss_limit)
        corrupt_safety_state = False
        for prefix, k in self._switches():
            k.day = state.kv_get(f"{prefix}_day", "") or ""
            try:
                k.start_equity = float(state.kv_get(f"{prefix}_start", "0") or 0)
                if (not math.isfinite(k.start_equity) or k.start_equity < 0
                        or (k.day and k.start_equity <= 0)):
                    raise ValueError("invalid persisted equity")
            except (TypeError, ValueError):
                k.start_equity = 0.0
                corrupt_safety_state = True
            halted = state.kv_get(f"{prefix}_halted", "0")
            if halted not in ("0", "1"):
                corrupt_safety_state = True
            k.halted = halted != "0"
        self.reconciled = False
        self._ks_dirty = False
        self._pending_flatten: dict[str, tuple[str, Fill | None]] = {}
        # An incomplete ledger requires operator reconciliation, including after a restart.
        accounting = state.kv_get("safety_accounting_halted", "0")
        self._accounting_halted = accounting != "0"
        if corrupt_safety_state or accounting not in ("0", "1"):
            self._halt_accounting()

    # ---------------------------------------------------------------- helpers
    def _now_iso(self) -> str:
        return self.feed.now().isoformat()

    def _switches(self):
        return (("ks", self.ks), ("ksw", self.ks_week), ("ksm", self.ks_month))

    def _persist_ks(self) -> None:
        values = {}
        for prefix, k in self._switches():
            values[f"{prefix}_day"] = k.day
            values[f"{prefix}_start"] = repr(k.start_equity)
            values[f"{prefix}_halted"] = "1" if k.halted else "0"
        self._ks_dirty = True
        try:
            self.state.kv_set_many(values)
        except Exception:
            # roll() has already changed memory. Never reopen entries on a retry that
            # sees the same day and would otherwise skip saving the new baseline.
            self._halt_accounting()
            raise
        self._ks_dirty = False

    @property
    def entries_halted(self) -> bool:
        return (self.ks.halted or self.ks_week.halted or self.ks_month.halted
                or bool(self._pending_flatten) or self._accounting_halted or self._ks_dirty)

    def _halt_accounting(self) -> None:
        self._accounting_halted = True
        try:
            self.state.kv_set("safety_accounting_halted", "1")
        except Exception:
            log.exception("could not persist accounting safety halt; entries remain halted in memory")

    def _emergency_flatten(self, symbol: str, reason: str, entry_fill: Fill | None = None) -> None:
        """Keep retrying a failed protective exit; do not discard its position or resting stops."""
        if symbol in self._pending_flatten:
            reason, pending_fill = self._pending_flatten[symbol]
            entry_fill = pending_fill or entry_fill
        self._pending_flatten[symbol] = (reason, entry_fill)
        try:
            self._flatten_symbol(symbol, reason, entry_fill=entry_fill)
        except Exception:
            log.exception("protective flatten failed for %s; entries halted, retrying every monitor tick", symbol)
        else:
            self._pending_flatten.pop(symbol, None)

    def _retry_protective_exits(self) -> None:
        for symbol, (reason, fill) in list(self._pending_flatten.items()):
            self._emergency_flatten(symbol, reason, fill)

    def _protect_or_flatten(self, pos: Position, *, force: bool = False) -> bool:
        """Restore protection before continuing; a failed stop immediately requests an exit."""
        try:
            if not force and pos.stop_id in self.broker.open_stop_ids(pos.symbol):
                return True
            last = self.feed.last_price(pos.symbol)
            if (pos.side > 0 and last <= pos.stop) or (pos.side < 0 and last >= pos.stop):
                self._emergency_flatten(pos.symbol, "stop_missing_breached")
                return False
            sid = self.broker.place_stop(pos.symbol, self._close_side(pos.side), pos.contracts, pos.stop)
            pos.stop_id = sid
            try:
                self.state.upsert_position(pos)
            except Exception:
                self._halt_accounting()
                raise
            # Replace before cancelling: a cancellation error must not remove the new protection.
            for old in self.broker.open_stop_ids(pos.symbol) - {sid}:
                self.broker.cancel_order(pos.symbol, old)
            return True
        except Exception:
            log.exception("stop protection failed for %s; flattening", pos.symbol)
            self._emergency_flatten(pos.symbol, "stop_failed_flatten")
            return False

    @staticmethod
    def _close_side(side: int) -> str:
        return "sell" if side > 0 else "buy"

    def _enrich(self, fill: Fill) -> Fill:
        """Live exchanges return fills without realized PnL. For a closing fill we know the entry
        price from state.db, so compute gross PnL (RULE 5 needs realized PnL in the ledger)."""
        if fill.reason == "entry" or fill.realized_pnl != 0:
            return fill
        pos = self.state.positions().get(fill.symbol)
        if pos is None:
            return fill
        cs = self.feed.contract_size(fill.symbol)
        fill.realized_pnl = pos.side * (fill.price - pos.entry) * fill.qty * cs
        return fill

    def _record(self, fill: Fill | None) -> None:
        if fill is not None:
            self.ledger.record(self._enrich(fill))

    # --------------------------------------------------------------- RULE 3
    def reconcile(self) -> list[str]:
        """Align state.db with the exchange. Must complete before any new order."""
        notes: list[str] = []
        self._process_fills()
        ex, db = self.broker.positions(), self.state.positions()

        for sym, p in db.items():
            if sym not in ex:  # closed while we were down (stop most likely)
                px = self.feed.last_price(sym)
                cs = self.feed.contract_size(sym)
                pnl = p.side * (px - p.entry) * p.contracts * cs
                self.ledger.record(Fill(self._now_iso(), sym, self._close_side(p.side), p.contracts, px,
                                        0.0, pnl, "reconcile_closed_offline_estimate", "reconcile"))
                self._cancel_stops(sym)
                self.state.delete_position(sym)
                notes.append(f"{sym}: in DB but flat on exchange -> removed (PnL estimated)")

        for sym, e in ex.items():
            d = db.get(sym)
            if d is None:
                if self.cfg.adopt_orphans:
                    stop = e.entry * (1 - e.side * ORPHAN_STOP_PCT)
                    pos = Position(sym, e.side, e.contracts, e.entry, stop, None, self._now_iso())
                    if self._protect_or_flatten(pos):
                        notes.append(f"{sym}: unknown exchange position ADOPTED with {ORPHAN_STOP_PCT:.0%} stop")
                else:
                    self._emergency_flatten(sym, "reconcile_flatten_orphan")
                    if sym not in self._pending_flatten:
                        notes.append(f"{sym}: unknown exchange position FLATTENED")
                continue
            changed = e.side != d.side or abs(e.contracts - d.contracts) > 1e-9
            if changed:
                notes.append(f"{sym}: size/side differ (db {d.side}x{d.contracts} vs exchange "
                             f"{e.side}x{e.contracts}) -> adopting exchange")
                d.side, d.contracts = e.side, e.contracts
            self._protect_or_flatten(d, force=changed)

        self.reconciled = True
        for n in notes:
            log.warning("reconcile: %s", n)
        if notes:
            self.notify("Reconcile: " + "; ".join(notes))
        return notes

    # --------------------------------------------------------------- fills/stops
    def _process_fills(self) -> None:
        for f in self.broker.pending_fills():
            try:
                self._record(f)
            except Exception:
                self._halt_accounting()
                raise
            self.broker.ack_fill(f)
            if f.reason == "stop":
                self.notify(f"STOP hit {f.symbol} @ {f.price:.2f} pnl {f.realized_pnl:.2f}")
                if f.symbol not in self.broker.positions():
                    self.state.delete_position(f.symbol)

    def _cancel_stops(self, symbol: str) -> None:
        for oid in self.broker.open_stop_ids(symbol):
            self.broker.cancel_order(symbol, oid)

    def _flatten_symbol(self, symbol: str, reason: str, entry_fill: Fill | None = None) -> None:
        e = self.broker.positions().get(symbol)
        fill = None
        if e:
            try:
                fill = self.broker.market_order(symbol, self._close_side(e.side), e.contracts,
                                                reduce_only=True, reason=reason)
            except Exception:
                # The close may have executed. Do not discard its accounting gap and
                # silently enter again after the next position query reports flat.
                self._halt_accounting()
                raise
        try:
            if entry_fill is not None:
                self._record(entry_fill)
                if symbol in self._pending_flatten:
                    self._pending_flatten[symbol] = (reason, None)
            self._record(fill)
        except Exception:
            self._halt_accounting()
            raise
        if symbol in self.broker.positions():
            raise RuntimeError(f"{symbol}: exit not flat; retaining state and exchange stops")
        self._cancel_stops(symbol)
        self.state.delete_position(symbol)

    def flatten_all(self, reason: str) -> None:
        for sym in list(self.broker.positions()):
            self._flatten_symbol(sym, reason)
        for sym in list(self.state.positions()):
            self.state.delete_position(sym)

    # ---------------------------------------------------------------- RULE 4
    def check_killswitch(self, now: pd.Timestamp) -> None:
        eq = self.broker.equity()
        iso = now.isocalendar()
        keys = {"daily": (self.ks, now.strftime("%Y-%m-%d")),
                "weekly": (self.ks_week, f"{iso[0]}-W{iso[1]:02d}"),
                "monthly": (self.ks_month, now.strftime("%Y-%m"))}
        for _, (k, key) in keys.items():
            if k.roll(key, eq):
                self._persist_ks()
        if self._ks_dirty:
            self._persist_ks()
        for name, (k, _) in keys.items():
            if k.check(eq):
                self._persist_ks()  # persist the halt BEFORE trying to flatten, so a crash cannot lose it
                self.notify(f"KILL-SWITCH: {name} drawdown {k.drawdown(eq):.2%} -> flattening, "
                            f"entries halted until next {name} period")
        # Flatten on the trip AND on every later tick while halted with positions left, so a failed
        # flatten (exchange error) is retried instead of being forgotten. Exchange stops still protect meanwhile.
        if any(k.halted for _, k in self._switches()) and self.broker.positions():
            try:
                self.flatten_all("kill_switch")
            except Exception as e:  # noqa: BLE001 - must not kill the loop; retried next tick
                log.error("kill-switch flatten failed, will retry next tick: %s", e)
                self.notify(f"KILL-SWITCH: flatten FAILED ({e}); retrying every tick, exchange stops remain")

    # ------------------------------------------------------------------ signals
    def _signal(self, symbol: str):
        df = self.feed.ohlcv_closed(symbol, getattr(self.model, "lookback", 600))
        if len(df) < getattr(self.model, "min_candles", 300):
            return None
        expected_last = self.feed.now().floor(f"{self.cfg.tf_minutes}min") - self.tf
        if df.index[-1] != expected_last:
            log.warning("%s: stale candles (last %s, expected %s) -> skipping", symbol,
                        df.index[-1], expected_last)
            return None
        nxt = df.index[-1] + self.tf  # the candle that is opening now; features see only closed data
        last = float(df["close"].iloc[-1])
        ext = pd.concat([df, pd.DataFrame({"open": last, "high": last, "low": last, "close": last,
                                           "volume": 0.0}, index=[nxt])])
        if hasattr(self.model, "predict_from_candles"):  # rule-based strategies
            out = self.model.predict_from_candles(ext)
            if out is None:
                return None
            p, atr_pct = out
        else:
            feats = build_features(ext).iloc[[-1]]
            p = self.model.predict_proba(feats).iloc[-1]
            atr_pct = float(feats["atr_pct"].iloc[-1])
        if p.isna().any() or atr_pct != atr_pct:
            return None
        return p, atr_pct

    # --------------------------------------------------------------------- step
    def step(self, now: pd.Timestamp) -> None:
        """Call once per candle, right after the previous candle closed."""
        if not self.reconciled:
            raise RuntimeError("reconcile() must complete before trading (RULE 3)")
        self._retry_protective_exits()
        self._process_fills()
        self.check_killswitch(now)
        self._manage_positions(now)
        if not self.entries_halted:
            self._look_for_entries(now)
        stamp = pd.Timestamp(now)
        stamp = stamp.tz_localize("UTC") if stamp.tzinfo is None else stamp.tz_convert("UTC")
        log.info("step complete candle %s", stamp.isoformat())

    def monitor(self, now: pd.Timestamp) -> None:
        """Between candles: evaluate resting stops (paper), book fills, watch the kill-switch."""
        if not self.reconciled:
            return
        self.broker.tick()
        self._process_fills()
        self._retry_protective_exits()
        live = self.broker.positions()
        stored = self.state.positions()
        for sym in live.keys() - stored.keys():
            # An order can execute even when its acknowledgment is lost.
            if sym not in self._pending_flatten:
                self._emergency_flatten(sym, "monitor_flatten_orphan")
        for sym, pos in stored.items():
            if sym in live and sym not in self._pending_flatten:
                self._protect_or_flatten(pos)
        self.check_killswitch(now)

    def _manage_positions(self, now: pd.Timestamp) -> None:
        live = self.broker.positions()
        for sym, pos in self.state.positions().items():
            if sym not in live:
                self.state.delete_position(sym)
                continue
            if sym in self._pending_flatten or not self._protect_or_flatten(pos):
                continue
            bars = int((now - pd.Timestamp(pos.opened_ts)) / self.tf)
            if bars >= self.cfg.horizon:
                self._flatten_symbol(sym, "time_exit")
                continue
            sig = self._signal(sym)
            if sig is not None and should_exit_on_flip(pos.side, sig[0]["p_down"], sig[0]["p_up"], self.cfg):
                self._flatten_symbol(sym, "model_flip")

    def _look_for_entries(self, now: pd.Timestamp) -> None:
        held = set(self.broker.positions())
        seen: dict[str, str] = {}  # heartbeat: what the strategy decided for each coin this candle
        try:
            self._scan(now, held, seen)
        finally:
            log.info("candle %s | equity %.2f | held %s | decisions %s", now.strftime("%m-%d %H:%M"),
                     self.broker.equity(), sorted(held) or "none", seen or "no data")

    def _scan(self, now: pd.Timestamp, held: set[str], seen: dict[str, str]) -> None:
        for sym in self.cfg.symbols:
            if self.entries_halted:
                break
            if len(held) >= self.cfg.max_positions:
                break
            if sym in held:
                continue
            sig = self._signal(sym)
            if sig is None:
                continue
            p, atr = sig
            side = decide(p["p_down"], p["p_up"], self.cfg)
            seen[sym.split("/")[0]] = {1: "BUY", -1: "SELL", 0: "stay out"}[side]
            if not side:
                continue
            price, cs = self.feed.last_price(sym), self.feed.contract_size(sym)
            if not self._venue_ok(sym, price):
                continue
            n = to_contracts(position_units(self.broker.equity(), price, atr, self.cfg), cs)
            if n <= 0:
                continue
            if n * cs * price * self.cfg.usdt_inr < self.cfg.min_order_inr:
                log.info("%s: order Rs %.0f below minimum Rs %.0f -> refused (capital too small for the "
                         "risk budget)", sym, n * cs * price * self.cfg.usdt_inr, self.cfg.min_order_inr)
                continue
            if not self._portfolio_ok(sym, side * n * cs * price):
                continue
            if self._enter(sym, side, n, atr, now):
                held.add(sym)

    def _portfolio_ok(self, sym: str, value: float) -> bool:
        """Gross exposure and correlation-aware expected-shortfall caps (bot/portfolio_risk.py). Can only block."""
        held = {s: p.side * p.contracts * self.feed.contract_size(s) * p.entry
                for s, p in self.broker.positions().items()}
        v = check_entry(held, sym, value, self.broker.equity(), self.feed.daily_closes, self.cfg)
        if not v.ok:
            log.info("%s: entry refused by portfolio risk: %s", sym, v.reason)
            return False
        log.info("%s: portfolio risk ok: %s%s", sym, v.reason, f", correlation with held {v.corr}" if v.corr else "")
        return True

    def _venue_ok(self, sym: str, signal_price: float) -> bool:
        if self.venue_price is None:
            return True
        try:
            vp = float(self.venue_price(sym))
        except Exception as exc:
            log.warning("%s: venue price unavailable (%s) -> no entry", sym, type(exc).__name__)
            return False
        if not all(math.isfinite(v) and v > 0 for v in (vp, signal_price)):
            log.warning("%s: invalid venue/signal price -> no entry", sym)
            return False
        dev = abs(vp / signal_price - 1)
        if dev > self.cfg.max_venue_deviation:
            log.warning("%s: venue/signal price mismatch %.2f%% -> no entry", sym, dev * 100)
            self.notify(f"{sym}: venue price off by {dev:.2%}, entry skipped")
            return False
        return True

    # ------------------------------------------------------------------- RULE 2
    def _enter(self, sym: str, side: int, contracts: int, atr: float, now: pd.Timestamp) -> bool:
        if self.entries_halted:
            return False
        try:
            fill = self.broker.market_order(sym, "buy" if side > 0 else "sell", contracts, reason="entry")
        except Exception:
            # A transport/parse failure is not proof the exchange rejected the order.
            self._halt_accounting()
            raise
        if fill is None:
            return False
        if (fill.symbol != sym or fill.side != ("buy" if side > 0 else "sell")
                or not all(math.isfinite(v) and v > 0 for v in (fill.qty, fill.price))
                or fill.qty > contracts):
            self._halt_accounting()
            self._emergency_flatten(sym, "invalid_entry_fill")
            raise RuntimeError("invalid exchange entry fill; reconcile account before resuming")
        contracts = fill.qty  # a partial market fill is the actual protected position
        stop = stop_price(side, fill.price, atr, self.cfg)
        try:
            sid = self.broker.place_stop(sym, self._close_side(side), contracts, stop)
        except Exception as exc:
            log.error("stop placement failed for %s: %s -> flattening", sym, exc)
            # The entry is not in the ledger yet. If this process dies while its emergency
            # exit is pending, startup can flatten the orphan but cannot recover that buy.
            # Persist the halt before attempting the exit; ledger reconciliation is manual.
            self._halt_accounting()
            self._emergency_flatten(sym, "stop_failed_flatten", entry_fill=fill)
            self.notify(f"{sym}: could not place exchange stop ({type(exc).__name__}); flattening")
            return False
        try:
            self.state.upsert_position(Position(sym, side, contracts, fill.price, stop, sid, now.isoformat()))
            self.ledger.record(fill)
        except Exception:
            self._halt_accounting()
            self._emergency_flatten(sym, "entry_persistence_failed")
            raise
        log.info("ENTER %s %s x%s @ %.2f stop %.2f", sym, "LONG" if side > 0 else "SHORT", contracts,
                 fill.price, stop)
        return True
