"""Recorded executions are acknowledged only after durable, idempotent accounting."""

import csv
import sqlite3
from types import SimpleNamespace

import pytest

from bot.broker.base import Fill
from bot.broker.delta import DeltaBroker
from bot.broker.paper import PaperBroker
from bot.ledger import Ledger
from bot.state import State
from tests.conftest import SYM


def fill(identity="paper:P10"):
    return Fill("2026-01-01T00:00:00+00:00", SYM, "sell", 1, 100, 0.1, -1,
                "stop", "same-order", fill_id=identity)


def test_paper_pending_stop_survives_ledger_error_and_process_restart(world, monkeypatch):
    broker = world["broker"]
    record = fill()
    broker.s["fills"] = [record.__dict__]
    broker._save()
    eng = world["make_engine"]()
    original = world["ledger"].record
    monkeypatch.setattr(world["ledger"], "record", lambda _: (_ for _ in ()).throw(OSError("disk failure")))
    with pytest.raises(OSError):
        eng._process_fills()
    reloaded = PaperBroker(world["feed"], world["cfg"], world["tmp"] / "ex.json")
    assert [f.fill_id for f in reloaded.pending_fills()] == [record.fill_id]
    eng.broker = reloaded
    monkeypatch.setattr(world["ledger"], "record", original)
    eng._process_fills()
    assert not reloaded.pending_fills()
    assert len(world["state"].fills()) == 1


def test_database_success_csv_failure_retry_is_idempotent(world, monkeypatch):
    ledger = world["ledger"]
    record = fill()
    original = ledger._export_csv
    monkeypatch.setattr(ledger, "_export_csv", lambda: (_ for _ in ()).throw(OSError("CSV disk failure")))
    with pytest.raises(OSError):
        ledger.record(record)
    assert len(world["state"].fills()) == 1
    monkeypatch.setattr(ledger, "_export_csv", original)
    ledger.record(record)
    assert len(world["state"].fills()) == 1
    with ledger.path.open(newline="") as fh:
        assert len(list(csv.DictReader(fh))) == 1


def test_distinct_identical_partial_executions_are_not_deduplicated(world):
    world["ledger"].record(fill("delta:trade-1"))
    world["ledger"].record(fill("delta:trade-2"))
    assert len(world["state"].fills()) == 2


def test_state_migrates_old_fill_schema_without_losing_rows(tmp_path):
    path = tmp_path / "old.db"
    with sqlite3.connect(path) as db:
        db.execute("CREATE TABLE fills (id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT, symbol TEXT, side TEXT,"
                   "qty REAL, price REAL, fee REAL, realized_pnl REAL, reason TEXT, order_id TEXT)")
        db.execute("INSERT INTO fills(ts,symbol,side,qty,price,fee,realized_pnl,reason,order_id)"
                   "VALUES ('t','BTC','buy',1,100,0,0,'entry','old')")
    state = State(path)
    assert len(state.fills()) == 1 and state.fills()[0]["fill_id"] == ""
    ledger = Ledger(tmp_path / "ledger.csv", state)
    ledger.record(fill())
    ledger.record(fill())
    assert len(state.fills()) == 2
    state.close()


def test_delta_pending_fills_keep_distinct_trades_on_one_order():
    broker = DeltaBroker.__new__(DeltaBroker)
    broker._seen, broker._seen_trades, broker._since_ms = set(), set(), 0
    trades = [{"id": i, "order": "same-order", "timestamp": 1, "symbol": SYM,
               "side": "sell", "amount": 1, "price": 100, "fee": {"cost": 0.1}}
              for i in ("trade-1", "trade-2")]
    broker.ex = SimpleNamespace(fetch_my_trades=lambda **kw: trades)
    pending = broker.pending_fills()
    assert len(pending) == 2 and len({f.fill_id for f in pending}) == 2
    broker.ack_fill(pending[0])
    assert [f.fill_id for f in broker.pending_fills()] == [pending[1].fill_id]


def test_exchange_execution_ids_are_namespaced_by_symbol():
    broker = DeltaBroker.__new__(DeltaBroker)
    broker._seen, broker._seen_trades, broker._since_ms = set(), set(), 0
    trades = [{"id": "trade-1", "order": "same-order", "timestamp": 1, "symbol": symbol,
               "side": "sell", "amount": 1, "price": 100, "fee": {"cost": 0.1}}
              for symbol in (SYM, "ETH/USD:USD")]
    broker.ex = SimpleNamespace(fetch_my_trades=lambda **kw: trades)
    pending = broker.pending_fills()
    assert len({f.fill_id for f in pending}) == 2
    broker.ack_fill(pending[0])
    assert [f.symbol for f in broker.pending_fills()] == ["ETH/USD:USD"]


def test_csv_only_historical_execution_is_never_silently_erased(world):
    ledger = world["ledger"]
    old = ("timestamp,pair,side,qty,price,fee,realized_pnl,reason,order_id\n"
           "2026-01-01T00:00:00+00:00,BTC/USD:USD,buy,1,100,0.1,0,entry,lost-db-write\n")
    ledger.path.write_text(old)
    original = ledger.path.read_bytes()
    with pytest.raises(RuntimeError, match="reconciliation"):
        ledger.record(fill())
    assert ledger.path.read_bytes() == original and world["state"].fills() == []
