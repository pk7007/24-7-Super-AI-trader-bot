"""Failure drills for exchange protection; all orders use the temporary paper broker."""

from dataclasses import replace

import pytest

from tests.conftest import SYM


def entered(world):
    eng = world["make_engine"]()
    eng.reconcile()
    eng.step(world["feed"].now())
    return eng


def fail(*args, **kwargs):
    raise ConnectionError("simulated exchange outage")


@pytest.mark.parametrize("path", ["manage", "reconcile", "monitor"])
def test_missing_stop_failure_flattens_in_each_recovery_path(world, monkeypatch, path):
    eng = entered(world)
    world["broker"].s["stops"].clear()
    monkeypatch.setattr(world["broker"], "place_stop", fail)
    if path == "manage":
        eng._manage_positions(world["feed"].now())
    elif path == "reconcile":
        eng.reconcile()
    else:
        eng.monitor(world["feed"].now())
    assert not world["broker"].positions()
    assert not world["state"].positions()


def test_stop_and_flatten_failure_blocks_entries_and_monitor_retries(world, monkeypatch):
    eng = entered(world)
    world["broker"].s["stops"].clear()
    original = world["broker"].market_order
    monkeypatch.setattr(world["broker"], "place_stop", fail)
    monkeypatch.setattr(world["broker"], "market_order", fail)
    eng._manage_positions(world["feed"].now())
    assert eng.entries_halted
    assert SYM in world["state"].positions()
    monkeypatch.setattr(world["broker"], "market_order", original)
    eng.monitor(world["feed"].now())
    assert not world["broker"].positions()
    assert not world["state"].positions()


def test_partial_flatten_keeps_state_and_resting_stop(world, monkeypatch):
    eng = entered(world)
    old = world["state"].positions()[SYM].stop_id
    monkeypatch.setattr(world["broker"], "market_order", lambda *a, **k: None)
    with pytest.raises(RuntimeError, match="not flat"):
        eng._flatten_symbol(SYM, "test_failed_flatten")
    assert SYM in world["state"].positions()
    assert old in world["broker"].open_stop_ids(SYM)


def test_entry_is_protected_before_ledger_failure_and_halts_on_accounting_error(world, monkeypatch):
    eng = world["make_engine"]()
    eng.reconcile()
    seen = []
    original = world["ledger"].record

    def record(fill):
        if fill.reason == "entry":
            seen.append(bool(world["broker"].open_stop_ids(SYM)))
            raise OSError("simulated ledger disk failure")
        return original(fill)

    monkeypatch.setattr(world["ledger"], "record", record)
    with pytest.raises(OSError):
        eng._enter(SYM, 1, 1, 0.02, world["feed"].now())
    assert seen == [True]
    assert not world["broker"].positions()
    assert eng.entries_halted
    assert world["make_engine"]().entries_halted  # never silently resume with an incomplete ledger


def test_orphan_adoption_stop_failure_flattens(world, monkeypatch):
    eng = world["make_engine"]()
    eng.cfg = replace(eng.cfg, adopt_orphans=True)
    world["broker"].market_order(SYM, "buy", 1, reason="orphan")
    monkeypatch.setattr(world["broker"], "place_stop", fail)
    eng.reconcile()
    assert not world["broker"].positions()


def test_entry_stop_and_flatten_failure_retries_from_monitor(world, monkeypatch):
    eng = world["make_engine"]()
    eng.reconcile()
    original = world["broker"].market_order

    def order(*args, **kwargs):
        if kwargs.get("reduce_only"):
            raise ConnectionError("close unavailable")
        return original(*args, **kwargs)

    monkeypatch.setattr(world["broker"], "place_stop", fail)
    monkeypatch.setattr(world["broker"], "market_order", order)
    assert eng._enter(SYM, 1, 1, 0.02, world["feed"].now()) is False
    assert eng.entries_halted
    monkeypatch.setattr(world["broker"], "market_order", original)
    eng.monitor(world["feed"].now())
    assert not world["broker"].positions()


def test_unrecorded_entry_halts_after_restart_even_when_orphan_exit_succeeds(world, monkeypatch):
    eng = world["make_engine"]()
    eng.reconcile()
    original = world["broker"].market_order

    def order(*args, **kwargs):
        if kwargs.get("reduce_only"):
            raise ConnectionError("close unavailable")
        return original(*args, **kwargs)

    monkeypatch.setattr(world["broker"], "place_stop", fail)
    monkeypatch.setattr(world["broker"], "market_order", order)
    assert eng._enter(SYM, 1, 1, 0.02, world["feed"].now()) is False
    assert world["state"].fills() == []  # the buy is still only in the failed process's memory
    monkeypatch.setattr(world["broker"], "market_order", original)
    restarted = world["make_engine"]()
    restarted.reconcile()  # closes the orphan; cannot reconstruct the missing entry from that exit
    assert not world["broker"].positions()
    assert restarted.entries_halted
    assert restarted._enter(SYM, 1, 1, 0.02, world["feed"].now()) is False
