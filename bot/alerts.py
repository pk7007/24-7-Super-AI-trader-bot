"""crypto-alerts: read-only watcher for the running paper/shadow bots.

Rings (once per event) on: no heartbeat for N minutes or a missing log, a failed candle step, a candle with
no data, a tripped daily/weekly/monthly kill-switch, every new fill, user price levels, and an open
position trading within 1% of its stop. Delivery goes through ``bot.notify.send`` (log + Telegram if
configured). It never writes bot state: SQLite is opened read-only; the only file it writes is
``state/alerts_fired.json`` (keys already rung). Idea adapted from trader-alerts in
github.com/Jakeschincariol/day-trader-skill (MIT); code written for this project.

Design rule: an alerting tool must never go quiet when something is wrong. Every rule runs in its own
guard; a rule that cannot run raises an ``alert_error`` alert instead of silencing the others.

Log timestamps are the bots' local time, so heartbeat age is measured against this machine's local time;
a negative age (clock or time-zone mismatch) is itself an alert.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sqlite3
import sys
import time
import urllib.parse
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable

ROOT = Path(__file__).resolve().parent.parent
LINE = re.compile(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}),\d+ (\w+) (\S+): (.*)$")
KS = {"ks": "daily", "ksw": "weekly", "ksm": "monthly"}
TAIL_BYTES = 400_000
HISTORY_KINDS = {"fill", "step_failed", "no_data"}   # past events (baselined if memory is lost)
REARM_PREFIXES = ("lvl:", "near:")                    # condition alerts that re-arm once they clear
EXIT_OK, EXIT_ALERTS, EXIT_DELIVERY_FAILED = 0, 10, 11


@dataclass
class Alert:
    kind: str
    key: str
    text: str


def _tail_lines(path: Path) -> list[str]:
    with path.open("rb") as fh:
        fh.seek(0, 2)
        size = fh.tell()
        fh.seek(max(0, size - TAIL_BYTES))
        return fh.read().decode("utf-8", errors="replace").splitlines()


class Alerts:
    def __init__(self, root: Path = ROOT, modes: tuple[str, ...] = ("paper", "shadow"), stale_min: float = 40,
                 near_stop_pct: float = 1.0, now_fn: Callable[[], datetime] = datetime.now,
                 send: Callable[[str], object] | None = None,
                 price_fn: Callable[[str], float] | None = "default"):  # type: ignore[assignment]
        self.root, self.modes, self.stale_min, self.near = Path(root), modes, stale_min, near_stop_pct / 100
        self.now_fn = now_fn
        if send is None:
            from .notify import send as _send
            send = _send
        self.send = send
        self.price_fn = _binance_price if price_fn == "default" else price_fn
        self.fired_path = self.root / "state" / "alerts_fired.json"
        self.delivery_failed = 0
        self.fired, self.memory_lost = self._load_fired()

    def _load_fired(self) -> tuple[list[str], bool]:
        if not self.fired_path.exists():
            return [], False
        try:
            data = json.loads(self.fired_path.read_text())
            if not isinstance(data, list) or not all(isinstance(k, str) for k in data):
                raise ValueError("not a list of strings")
            return data, False
        except Exception:
            backup = self.fired_path.with_name(f"alerts_fired.corrupt-{self.now_fn():%Y%m%d-%H%M%S}.json")
            try:
                self.fired_path.replace(backup)
            except OSError:
                pass
            return [], True

    def _hour(self) -> str:
        return self.now_fn().strftime("%Y-%m-%d %H")

    def _err(self, rule: str, mode: str, e: Exception) -> Alert:
        return Alert("alert_error", f"err:{rule}:{mode}:{type(e).__name__}:{self._hour()}",
                     f"ALERT CHECK FAILED {mode}/{rule}: {type(e).__name__}: {str(e)[:160]} - this check is blind until fixed")

    # ------------------------------------------------------------------ rules
    def _log_rules(self, mode: str) -> list[Alert]:
        log = self.root / "state" / f"{mode}.log"
        day = self.now_fn().strftime("%Y-%m-%d")
        if not log.exists():
            return [Alert("heartbeat", f"nolog:{mode}:{day}", f"HEARTBEAT {mode}: no log at {log} - is the bot running?")]
        out, last_candle, matched = [], None, 0
        lines = _tail_lines(log)
        for ln in lines:
            m = LINE.match(ln)
            if not m:
                continue
            matched += 1
            ts, _level, logger, msg = m.groups()
            if logger == "engine" and msg.startswith("candle "):
                last_candle = ts
                if "decisions no data" in msg:
                    out.append(Alert("no_data", f"nodata:{mode}:{ts}", f"DATA {mode}: candle at {ts} had no data; no decisions made"))
            elif logger == "main" and msg.startswith("step failed"):
                out.append(Alert("step_failed", f"step:{mode}:{ts}", f"STEP FAILED {mode} at {ts}: see state/{mode}.log"))
        if len(lines) > 50 and matched == 0:
            out.append(Alert("alert_error", f"format:{mode}:{day}",
                             f"ALERT CHECK FAILED {mode}: none of the last {len(lines)} log lines match the expected format; log format changed?"))
        if last_candle is None:
            out.append(Alert("heartbeat", f"nocandle:{mode}:{day}", f"HEARTBEAT {mode}: log has no candle line"))
        else:
            age = (self.now_fn() - datetime.strptime(last_candle, "%Y-%m-%d %H:%M:%S")).total_seconds() / 60
            if age < -2:
                out.append(Alert("alert_error", f"clock:{mode}:{day}",
                                 f"CLOCK {mode}: last candle {last_candle} is {-age:.0f} min in the future; checker and bot clocks or time zones differ, heartbeat unreliable"))
            elif age > self.stale_min:
                remind = int(age // 360)  # rings when stale, then a reminder every 6 hours of the same outage
                out.append(Alert("heartbeat", f"stale:{mode}:{last_candle}:{remind}",
                                 f"HEARTBEAT {mode}: no candle for {age:.0f} min (last {last_candle}); bot stopped, PC asleep or data feed down"))
        return out

    def _db(self, mode: str) -> sqlite3.Connection | None:
        p = self.root / "state" / mode / "state.db"
        if not p.exists():
            return None
        db = sqlite3.connect(f"file:{urllib.parse.quote(p.as_posix())}?mode=ro", uri=True)
        db.row_factory = sqlite3.Row
        return db

    def _kill_switch(self, mode: str) -> list[Alert]:
        db = self._db(mode)
        if db is None:
            if (self.root / "state" / f"{mode}.log").exists():
                return [Alert("alert_error", f"nodb:{mode}:{self.now_fn():%Y-%m-%d}",
                              f"ALERT CHECK FAILED {mode}: log exists but state/{mode}/state.db is missing; kill-switch status unknown")]
            return []
        try:
            kv = {r["key"]: r["value"] for r in db.execute("SELECT key, value FROM kv")}
        finally:
            db.close()
        return [Alert("kill_switch", f"ks:{mode}:{p}:{kv.get(p + '_day') or self._hour()}",
                      f"KILL-SWITCH {mode}: {name} loss limit tripped ({kv.get(p + '_day', '?')}); entries halted, positions flattened")
                for p, name in KS.items() if kv.get(f"{p}_halted") == "1"]

    def _fills(self, mode: str) -> list[Alert]:
        p = self.root / "state" / mode / "trades_ledger.csv"
        if not p.exists():
            return []
        out = []
        with p.open(encoding="utf-8", newline="") as fh:
            for i, r in enumerate(csv.DictReader(fh), start=2):  # row 1 is the header
                key = f"fill:{mode}:{r.get('order_id') or ''}:{i}"
                try:
                    text = (f"FILL {mode}: {r['side']} {r['qty']} {r['pair'].split('/')[0]} @ {float(r['price']):,.2f} "
                            f"({r.get('reason') or ''}), realized {float(r.get('realized_pnl') or 0):+.2f} USD")
                    out.append(Alert("fill", key, text))
                except Exception as e:  # unreadable row: say so, keep going
                    out.append(Alert("alert_error", f"badrow:{mode}:{i}",
                                     f"ALERT CHECK FAILED {mode}: ledger row {i} unreadable ({type(e).__name__}); check trades_ledger.csv"))
        return out

    def _prices(self) -> tuple[list[Alert], bool]:
        """Returns (alerts, evaluated). evaluated=False means prices could not be checked (no re-arming)."""
        if self.price_fn is None:
            return [], False
        wanted: list[tuple[str, str, float, str]] = []  # (symbol, kind, level, key)
        lv = self.root / "alerts_levels.json"
        if lv.exists():
            for x in json.loads(lv.read_text()):
                for side in ("above", "below"):
                    if side in x:
                        lvl = float(x[side])
                        wanted.append((x["symbol"], side, lvl, f"lvl:{x['symbol']}:{side}:{lvl}"))
        for mode in self.modes:
            db = self._db(mode)
            if db is None:
                continue
            try:
                for r in db.execute("SELECT symbol, side, stop, opened_ts FROM positions"):
                    kind = "near_stop" if int(r["side"]) > 0 else "near_stop_short"
                    wanted.append((r["symbol"], kind, float(r["stop"]), f"near:{mode}:{r['opened_ts']}:{r['symbol']}"))
            finally:
                db.close()
        if not wanted:
            return [], True
        out, cache = [], {}
        for sym, kind, level, key in wanted:
            try:
                px = cache[sym] if sym in cache else cache.setdefault(sym, float(self.price_fn(sym)))
            except Exception as e:  # one alert per hour, not one per symbol
                return [Alert("price_unavailable", f"noprice:{self._hour()}",
                              f"PRICE CHECK FAILED ({type(e).__name__}); level and stop alerts paused")], False
            base = sym.split("/")[0]
            if kind == "above" and px >= level:
                out.append(Alert("level", key, f"LEVEL {base} {px:,.2f} is above {level:,.2f}"))
            elif kind == "below" and px <= level:
                out.append(Alert("level", key, f"LEVEL {base} {px:,.2f} is below {level:,.2f}"))
            elif (kind == "near_stop" and px <= level * (1 + self.near)) or \
                    (kind == "near_stop_short" and px >= level * (1 - self.near)):
                out.append(Alert("near_stop", key,  # long: price falling to stop; short: rising to it
                                 f"NEAR STOP {base} {px:,.2f} within {self.near:.0%} of stop {level:,.2f} ({key.split(':')[1]})"))
        return out, True

    # ------------------------------------------------------------------ main
    def check(self) -> list[Alert]:
        found: list[Alert] = []
        for mode in self.modes:
            for name, rule in (("log", self._log_rules), ("killswitch", self._kill_switch), ("ledger", self._fills)):
                try:
                    found += rule(mode)
                except Exception as e:
                    found.append(self._err(name, mode, e))
        try:
            price_alerts, evaluated = self._prices()
            found += price_alerts
        except Exception as e:
            found.append(self._err("prices", "all", e))
            evaluated = False

        if evaluated:  # re-arm level / near-stop alerts whose condition has cleared
            live = {a.key for a in found}
            self.fired = [k for k in self.fired if not (k.startswith(REARM_PREFIXES) and k not in live)]

        changed, reset_key = False, None
        if self.memory_lost:  # do not re-send history after losing memory; say so (retried until delivered)
            past = [a for a in found if a.kind in HISTORY_KINDS and a.key not in self.fired]
            self.fired += [a.key for a in past]
            counts = {k: sum(a.kind == k for a in past) for k in sorted(HISTORY_KINDS)}
            reset_key = f"memory:{self.now_fn():%Y-%m-%d}"
            found.append(Alert("alert_error", reset_key,
                               f"ALERT MEMORY RESET: alerts_fired.json was unreadable (backed up); past events recorded "
                               f"without re-sending: {counts}. Check the ledger for fills you have not seen. "
                               f"Current problems are still reported."))
            changed = True

        new = [a for a in found if a.key not in self.fired]
        sent = []
        for a in new:
            ok = self.send(a.text)
            if ok is False:  # a configured channel failed: do not mark it, so it is retried next check
                self.delivery_failed += 1
                continue
            self.fired.append(a.key)
            sent.append(a)
        if reset_key and reset_key in self.fired:
            self.memory_lost = False  # only once the reset notice itself was delivered
        if sent or changed or evaluated:
            self._save()
        return new

    def _save(self) -> None:
        self.fired = self.fired[-5000:]
        self.fired_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.fired_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.fired))
        tmp.replace(self.fired_path)


def _binance_price(symbol: str) -> float:
    """Public last price (no key). BTC/USD:USD -> BTCUSDT."""
    import urllib.request

    pair = symbol.split("/")[0] + "USDT"
    with urllib.request.urlopen(f"https://api.binance.com/api/v3/ticker/price?symbol={pair}", timeout=10) as r:
        return float(json.loads(r.read())["price"])


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="python -m bot.alerts", description="Read-only alerts for the paper/shadow bots")
    sub = p.add_subparsers(dest="cmd", required=True)
    for name in ("check", "watch"):
        c = sub.add_parser(name)
        c.add_argument("--stale-min", type=float, default=40)
        c.add_argument("--no-price", action="store_true", help="skip level and near-stop checks (no network)")
        c.add_argument("--json", action="store_true")
        if name == "watch":
            c.add_argument("--every", type=float, default=300, help="seconds between checks")
    a = p.parse_args(argv)
    al = Alerts(stale_min=a.stale_min, price_fn=None if a.no_price else "default")  # type: ignore[arg-type]
    while True:
        try:
            new = al.check()
        except Exception as e:  # last line of defence: never die silently
            new = [Alert("alert_error", "watcher", f"ALERT WATCHER ERROR: {type(e).__name__}: {e}")]
            try:
                al.send(new[0].text)
            except Exception:
                pass
        if a.json:
            print(json.dumps([asdict(x) for x in new]))
        else:
            for x in new:
                print(x.text)
            if not new and a.cmd == "check":
                print("no new alerts")
            if al.delivery_failed:
                print(f"WARNING: {al.delivery_failed} alert(s) could not be delivered to Telegram; they will be retried",
                      file=sys.stderr)
        sys.stdout.flush()
        if a.cmd == "check":
            return EXIT_DELIVERY_FAILED if al.delivery_failed else (EXIT_ALERTS if new else EXIT_OK)
        al.delivery_failed = 0
        time.sleep(a.every)


if __name__ == "__main__":
    sys.exit(main())
