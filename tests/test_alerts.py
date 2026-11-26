"""crypto-alerts: heartbeat, step failures, stale data, kill-switch, fills, price levels. Each rings once."""

import csv
import hashlib
import sqlite3
from datetime import datetime, timedelta

import pytest

from bot.alerts import Alerts

NOW = datetime(2026, 11, 25, 10, 0, 0)


def _line(ts: datetime, logger: str, msg: str, level: str = "INFO") -> str:
    return f"{ts:%Y-%m-%d %H:%M:%S},123 {level} {logger}: {msg}\n"


def _candle(ts: datetime, decisions: str = "{'BTC': 'stay out'}") -> str:
    return _line(ts, "engine", f"candle 11-25 04:15 | equity 113.60 | held none | decisions {decisions}")


@pytest.fixture
def root(tmp_path):
    (tmp_path / "state" / "paper").mkdir(parents=True)
    (tmp_path / "state" / "shadow").mkdir(parents=True)
    for m in ("paper", "shadow"):
        (tmp_path / "state" / f"{m}.log").write_text(_candle(NOW - timedelta(minutes=5)))
        _kv(tmp_path, m).close()  # a running bot always has its state.db
    return tmp_path


def make(root, **kw):
    kw.setdefault("price_fn", None)
    return Alerts(root, now_fn=lambda: NOW, send=lambda m: None, **kw)


def test_fresh_heartbeat_is_quiet(root):
    assert make(root).check() == []


def test_stale_heartbeat_rings_once_then_again_only_after_recovery(root):
    (root / "state" / "paper.log").write_text(_candle(NOW - timedelta(minutes=55)))
    a = make(root)
    first = a.check()
    assert [x.kind for x in first] == ["heartbeat"] and "paper" in first[0].text and "55 min" in first[0].text
    assert a.check() == []  # same outage: no spam
    # recovery then a new outage rings again
    (root / "state" / "paper.log").write_text(_candle(NOW - timedelta(minutes=50)) + _candle(NOW - timedelta(minutes=45)))
    assert [x.kind for x in a.check()] == ["heartbeat"]


def test_missing_log_fails_loud_not_silent(root):
    (root / "state" / "shadow.log").unlink()
    out = make(root).check()
    assert [x.kind for x in out] == ["heartbeat"] and "no log" in out[0].text


def test_step_failure_and_no_data_ring_once_each(root):
    log = root / "state" / "paper.log"
    log.write_text(_candle(NOW - timedelta(minutes=20), "no data")
                   + _line(NOW - timedelta(minutes=20), "main", "step failed", "ERROR")
                   + _candle(NOW - timedelta(minutes=5)))
    a = make(root)
    kinds = sorted(x.kind for x in a.check())
    assert kinds == ["no_data", "step_failed"]
    assert a.check() == []


def _kv(root, mode, **pairs):
    db = sqlite3.connect(root / "state" / mode / "state.db")
    db.execute("CREATE TABLE IF NOT EXISTS kv (key TEXT PRIMARY KEY, value TEXT)")
    db.execute("CREATE TABLE IF NOT EXISTS positions (symbol TEXT PRIMARY KEY, side INTEGER, contracts REAL,"
               " entry REAL, stop REAL, stop_id TEXT, opened_ts TEXT)")
    for k, v in pairs.items():
        db.execute("INSERT OR REPLACE INTO kv VALUES (?,?)", (k, v))
    db.commit()
    return db


def test_kill_switch_rings_once_per_period(root):
    _kv(root, "paper", ksw_halted="1", ksw_day="2026-W48").close()
    a = make(root)
    out = a.check()
    assert [x.kind for x in out] == ["kill_switch"] and "weekly" in out[0].text
    assert a.check() == []


def test_new_fill_rings_once(root):
    p = root / "state" / "paper" / "trades_ledger.csv"
    with p.open("w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["timestamp", "pair", "side", "qty", "price", "fee", "realized_pnl", "reason", "order_id"])
        w.writerow(["2026-11-25T04:15:00+00:00", "BTC/USD:USD", "buy", "0.0002", "90000", "0.02", "0", "entry", "P1"])
    a = make(root)
    out = a.check()
    assert [x.kind for x in out] == ["fill"] and "buy" in out[0].text and "BTC" in out[0].text
    assert a.check() == []


def test_price_levels_and_near_stop(root):
    (root / "alerts_levels.json").write_text('[{"symbol": "BTC/USD:USD", "above": 100000}]')
    db = _kv(root, "paper")
    db.execute("INSERT INTO positions VALUES ('ETH/USD:USD', 1, 0.01, 3000, 2900, 'P2', 'x')")
    db.commit(); db.close()
    prices = {"BTC/USD:USD": 100500.0, "ETH/USD:USD": 2915.0}  # ETH within 1% of its 2900 stop
    a = make(root, price_fn=lambda s: prices[s])
    kinds = sorted(x.kind for x in a.check())
    assert kinds == ["level", "near_stop"]
    assert a.check() == []


def test_price_failure_rings_once_not_per_symbol(root):
    (root / "alerts_levels.json").write_text('[{"symbol": "BTC/USD:USD", "above": 1}, {"symbol": "ETH/USD:USD", "below": 1}]')

    def boom(_):
        raise RuntimeError("network down")

    a = make(root, price_fn=boom)
    out = a.check()
    assert [x.kind for x in out] == ["price_unavailable"]
    assert a.check() == []


def test_check_never_modifies_bot_state(root):
    db = _kv(root, "paper", ks_halted="1", ks_day="2026-11-25")
    db.close()
    (root / "state" / "paper" / "paper_exchange.json").write_text('{"cash": 113.6}')
    files = [root / "state" / "paper" / "state.db", root / "state" / "paper" / "paper_exchange.json",
             root / "state" / "paper.log"]
    before = [hashlib.sha256(f.read_bytes()).hexdigest() for f in files]
    make(root).check()
    assert [hashlib.sha256(f.read_bytes()).hexdigest() for f in files] == before


def test_alerts_are_delivered_through_send(root):
    (root / "state" / "paper.log").write_text(_candle(NOW - timedelta(hours=2)))
    sent = []
    Alerts(root, now_fn=lambda: NOW, send=sent.append, price_fn=None).check()
    assert len(sent) == 1 and sent[0].startswith("HEARTBEAT")


def test_near_stop_handles_short_positions(root):
    db = _kv(root, "paper")
    db.execute("INSERT INTO positions VALUES ('SOL/USD:USD', -1, 1, 200, 210, 'P3', 'y')")  # short, stop above
    db.commit(); db.close()
    assert make(root, price_fn=lambda s: 190.0).check() == []          # far from stop
    assert [x.kind for x in make(root, price_fn=lambda s: 208.5).check()] == ["near_stop"]  # within 1% below 210


# ---------------------------------------------------------------- silent-failure review fixes (F1-F9)
def test_bad_ledger_row_alerts_and_does_not_silence_other_checks(root):  # F1
    (root / "state" / "shadow.log").unlink()
    p = root / "state" / "paper" / "trades_ledger.csv"
    p.write_text("timestamp,pair,side,qty,price,fee,realized_pnl,reason,order_id\n"
                 "t,BTC/USD:USD,buy,1,abc,0,0,entry,P1\n"
                 "t,ETH/USD:USD,buy,1,3000,0,0,entry,P2\n")
    kinds = sorted(x.kind for x in make(root).check())
    assert kinds == ["alert_error", "fill", "heartbeat"]  # bad row flagged, good row and shadow heartbeat still ring


def test_corrupt_state_db_alerts_instead_of_silence(root):  # F2
    (root / "state" / "paper" / "state.db").write_bytes(b"this is not sqlite" * 100)
    out = make(root).check()
    assert any(x.kind == "alert_error" and "killswitch" in x.text for x in out)


def test_missing_db_with_live_log_alerts(root):  # F2
    for m in ("paper", "shadow"):
        (root / "state" / m / "state.db").unlink()
    out = make(root).check()
    assert sorted(x.kind for x in out) == ["alert_error", "alert_error"]  # both modes: log exists, no state.db
    assert all("state.db is missing" in x.text for x in out)


def test_failed_delivery_is_retried_not_marked_fired(root):  # F3
    (root / "state" / "paper.log").write_text(_candle(NOW - timedelta(hours=2)))
    _kv(root, "paper").close(); _kv(root, "shadow").close()
    a = Alerts(root, now_fn=lambda: NOW, send=lambda m: False, price_fn=None)
    assert len(a.check()) == 1 and a.delivery_failed == 1
    sent = []
    b = Alerts(root, now_fn=lambda: NOW, send=lambda m: sent.append(m) or True, price_fn=None)
    assert len(b.check()) == 1 and sent  # retried on the next run


def test_corrupt_memory_baselines_history_instead_of_respamming(root):  # F4
    _kv(root, "paper").close(); _kv(root, "shadow").close()
    (root / "state" / "paper.log").write_text(_line(NOW - timedelta(minutes=30), "main", "step failed", "ERROR")
                                              + _candle(NOW - timedelta(minutes=5)))
    (root / "state" / "alerts_fired.json").write_text("{not json")
    out = make(root).check()
    assert [x.kind for x in out] == ["alert_error"] and "MEMORY RESET" in out[0].text
    assert list((root / "state").glob("alerts_fired.corrupt-*.json"))
    assert make(root).check() == []


def test_level_rearms_after_condition_clears_and_survives_file_edits(root):  # F5
    _kv(root, "paper").close(); _kv(root, "shadow").close()
    (root / "alerts_levels.json").write_text('[{"symbol": "BTC/USD:USD", "above": 100}]')
    px = {"v": 101.0}
    f = lambda s: px["v"]
    assert [x.kind for x in make(root, price_fn=f).check()] == ["level"]
    (root / "alerts_levels.json").write_text('[{"symbol": "ETH/USD:USD", "below": 1}, {"symbol": "BTC/USD:USD", "above": 100}]')
    assert make(root, price_fn=f).check() == []  # reordering the file does not re-fire
    px["v"] = 99.0
    assert make(root, price_fn=f).check() == []  # cleared: re-arms silently
    px["v"] = 102.0
    assert [x.kind for x in make(root, price_fn=f).check()] == ["level"]  # crosses again: rings again


def test_two_fills_with_same_timestamp_and_no_order_id_both_ring(root):  # F5
    _kv(root, "paper").close(); _kv(root, "shadow").close()
    (root / "state" / "paper" / "trades_ledger.csv").write_text(
        "timestamp,pair,side,qty,price,fee,realized_pnl,reason,order_id\n"
        "t,BTC/USD:USD,buy,1,100,0,0,entry,\nt,BTC/USD:USD,sell,1,101,0,1,flip,\n")
    assert [x.kind for x in make(root).check()] == ["fill", "fill"]


def test_future_timestamp_is_flagged_not_silent(root):  # F6
    _kv(root, "paper").close(); _kv(root, "shadow").close()
    (root / "state" / "paper.log").write_text(_candle(NOW + timedelta(hours=5, minutes=30)))  # e.g. IST log, UTC checker
    out = make(root).check()
    assert [x.kind for x in out] == ["alert_error"] and "CLOCK" in out[0].text


def test_log_format_change_is_flagged(root):  # F8
    _kv(root, "paper").close(); _kv(root, "shadow").close()
    (root / "state" / "paper.log").write_text("".join(f"[{i}] something else\n" for i in range(60)))
    kinds = sorted(x.kind for x in make(root).check())
    assert kinds == ["alert_error", "heartbeat"]


def test_cli_exit_codes_do_not_collide_with_argparse(root, monkeypatch):  # F9
    import bot.alerts as m
    monkeypatch.setattr(m, "ROOT", root)
    monkeypatch.setattr(m.Alerts.__init__, "__defaults__",
                        (root, ("paper", "shadow"), 40, 1.0, lambda: NOW, lambda t: True, "default"))
    _kv(root, "paper").close(); _kv(root, "shadow").close()
    assert m.main(["check", "--no-price"]) == m.EXIT_OK
    (root / "state" / "paper.log").write_text(_candle(NOW - timedelta(hours=3)))
    assert m.main(["check", "--no-price"]) == m.EXIT_ALERTS


def test_long_outage_reminds_every_6_hours(root):  # F5 reminder
    (root / "state" / "paper.log").write_text(_candle(NOW - timedelta(hours=1)))
    later = {"t": NOW}
    a = Alerts(root, modes=("paper",), now_fn=lambda: later["t"], send=lambda m: True, price_fn=None)
    assert [x.kind for x in a.check()] == ["heartbeat"]
    later["t"] = NOW + timedelta(hours=2)
    assert a.check() == []
    later["t"] = NOW + timedelta(hours=6)
    assert [x.kind for x in a.check()] == ["heartbeat"]


def test_memory_reset_notice_is_retried_until_delivered(root):  # F10
    (root / "state" / "alerts_fired.json").write_text("{bad")
    a = Alerts(root, now_fn=lambda: NOW, send=lambda m: False, price_fn=None)
    a.check()
    a.send = lambda m: True
    assert any("MEMORY RESET" in x.text for x in a.check())
