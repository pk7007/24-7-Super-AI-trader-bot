"""Offline drills for malformed exchange/state inputs and partial execution."""

from dataclasses import replace
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from bot.broker.delta import DeltaBroker
from bot.config import Settings
from bot.portfolio_risk import check_entry
from bot.risk import position_units, to_contracts
from tests.conftest import SYM


@pytest.mark.parametrize("price", [float("nan"), float("inf"), 0.0, -1.0])
def test_invalid_execution_venue_price_blocks_entry(world, price):
    eng = world["make_engine"]()
    eng.venue_price = lambda _: price
    assert eng._venue_ok(SYM, 60000.0) is False


@pytest.mark.parametrize("key,value", [("ks_halted", "garbled"), ("ksw_halted", "true"),
                                     ("ksm_halted", "2"), ("safety_accounting_halted", "bad"),
                                     ("ks_start", "nan")])
def test_corrupted_persisted_safety_state_never_reopens_entries(world, key, value):
    world["state"].kv_set(key, value)
    eng = world["make_engine"]()
    eng.reconcile()
    eng.check_killswitch(world["feed"].now())
    assert eng.entries_halted


def test_partial_entry_stop_and_database_use_actual_fill_quantity(world, monkeypatch):
    broker = world["broker"]
    original = broker.market_order

    def partial(symbol, side, contracts, **kw):
        return original(symbol, side, contracts / 2, **kw)

    monkeypatch.setattr(broker, "market_order", partial)
    eng = world["make_engine"]()
    eng.reconcile()
    assert eng._enter(SYM, 1, 10, 0.02, world["feed"].now())
    pos = world["state"].positions()[SYM]
    assert pos.contracts == 5
    assert broker.s["stops"][pos.stop_id]["contracts"] == 5


@pytest.mark.parametrize("equity,price,atr", [(np.inf, 100, 0.01), (np.nan, 100, 0.01),
                                            (100, np.inf, 0.01), (100, np.nan, 0.01),
                                            (100, 100, np.inf)])
def test_nonfinite_sizing_inputs_refuse_orders(equity, price, atr):
    assert position_units(equity, price, atr, Settings()) == 0


@pytest.mark.parametrize("units,step", [(np.nan, 0.001), (np.inf, 0.001), (1, np.nan), (1, 0)])
def test_bad_lot_inputs_return_zero_instead_of_crashing(units, step):
    assert to_contracts(units, step) == 0


@pytest.mark.parametrize("equity,value", [(np.nan, 10), (np.inf, 10), (100, np.nan), (100, np.inf)])
def test_portfolio_checks_fail_closed_for_nonfinite_balances(equity, value):
    dates = pd.date_range("2026-01-01", periods=60, tz="UTC")
    closes = pd.Series(np.linspace(100, 110, 60), index=dates)
    result = check_entry({}, SYM, value, equity, lambda *a: closes, Settings())
    assert result.ok is False


@pytest.mark.parametrize("filled", [0, None, float("nan")])
def test_delta_never_invents_requested_fill_quantity(filled):
    broker = DeltaBroker.__new__(DeltaBroker)
    broker._seen = set()
    broker.ex = SimpleNamespace(create_order=lambda *a: {
        "id": "order-1", "filled": filled, "average": 100.0, "status": "open"})
    with pytest.raises(RuntimeError):
        broker.market_order(SYM, "buy", 10, reason="entry")


def test_uncertain_market_acknowledgment_halts_and_monitor_flattens_orphan(world, monkeypatch):
    broker = world["broker"]
    original = broker.market_order

    def uncertain(*args, **kwargs):
        original(*args, **kwargs)
        raise ConnectionError("acknowledgment lost after fill")

    eng = world["make_engine"]()
    eng.reconcile()
    monkeypatch.setattr(broker, "market_order", uncertain)
    with pytest.raises(ConnectionError):
        eng._enter(SYM, 1, 2, 0.02, world["feed"].now())
    assert eng.entries_halted and world["make_engine"]().entries_halted
    monkeypatch.setattr(broker, "market_order", original)
    eng.monitor(world["feed"].now())
    assert not broker.positions()


def test_nonpositive_persisted_loss_baseline_for_existing_period_halts(world):
    world["state"].kv_set("ks_day", world["feed"].now().strftime("%Y-%m-%d"))
    world["state"].kv_set("ks_start", "0")
    eng = world["make_engine"]()
    assert eng.entries_halted


def test_loss_switch_snapshot_rolls_back_as_one_transaction(world):
    import sqlite3
    eng = world["make_engine"]()
    eng.check_killswitch(world["feed"].now())
    old = world["state"].kv_get("ks_day")
    world["state"].db.execute("CREATE TRIGGER fail_last_switch BEFORE UPDATE ON kv "
                              "WHEN NEW.key = 'ksm_start' BEGIN SELECT RAISE(ABORT, 'simulated write failure'); END")
    eng.ks.day = "2099-01-01"
    with pytest.raises(sqlite3.IntegrityError):
        eng._persist_ks()
    assert world["state"].kv_get("ks_day") == old


def test_failed_rollover_snapshot_never_resumes_without_persistence(world, monkeypatch):
    eng = world["make_engine"]()
    now = world["feed"].now()
    eng.check_killswitch(now)
    original = world["state"].kv_set_many
    calls = []

    def fail_once(values):
        calls.append(values)
        if len(calls) == 1:
            raise OSError("risk snapshot unavailable")
        return original(values)

    monkeypatch.setattr(world["state"], "kv_set_many", fail_once)
    tomorrow = now + pd.Timedelta(days=1)  # same week/month, only the daily switch rolls
    with pytest.raises(OSError):
        eng.check_killswitch(tomorrow)
    assert eng.entries_halted
    eng.check_killswitch(tomorrow)
    assert len(calls) == 2
    assert world["state"].kv_get("ks_day") == tomorrow.strftime("%Y-%m-%d")
    assert world["make_engine"]().entries_halted  # an uncertain baseline needs operator review


def test_uncertain_exit_acknowledgment_halts_across_restart(world, monkeypatch):
    eng = world["make_engine"]()
    eng.reconcile()
    eng.step(world["feed"].now())
    original = world["broker"].market_order

    def close_then_lose_ack(*args, **kwargs):
        original(*args, **kwargs)
        raise ConnectionError("exit executed but acknowledgment lost")

    monkeypatch.setattr(world["broker"], "market_order", close_then_lose_ack)
    with pytest.raises(ConnectionError):
        eng._flatten_symbol(SYM, "time_exit")
    assert not world["broker"].positions()
    assert eng.entries_halted and world["make_engine"]().entries_halted


def test_failed_candle_never_emits_completion_evidence(world, monkeypatch, caplog):
    eng = world["make_engine"]()
    eng.reconcile()
    monkeypatch.setattr(eng, "_manage_positions", lambda _: (_ for _ in ()).throw(ConnectionError("offline failure")))
    with caplog.at_level("INFO", logger="engine"), pytest.raises(ConnectionError):
        eng.step(world["feed"].now())
    assert "step complete candle" not in caplog.text


@pytest.mark.parametrize("halted", [False, True])
def test_successful_candle_emits_full_timestamp_even_when_entries_halted(world, halted, caplog):
    eng = world["make_engine"]()
    eng.reconcile()
    eng._accounting_halted = halted
    with caplog.at_level("INFO", logger="engine"):
        eng.step(world["feed"].now())
    assert f"step complete candle {world['feed'].now().isoformat()}" in caplog.text
