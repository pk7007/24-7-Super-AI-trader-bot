import csv

import pytest

from bot.state import State
from tests.conftest import SYM


def _enter(w):
    eng = w["make_engine"]()
    eng.reconcile()
    ts = w["feed"].now()
    eng.step(ts)
    return eng, ts


def test_rule3_step_refuses_before_reconcile(world):
    eng = world["make_engine"]()
    with pytest.raises(RuntimeError):
        eng.step(world["feed"].now())
    assert not world["broker"].positions()


def test_rule2_entry_attaches_exchange_side_stop(world):
    eng, _ = _enter(world)
    pos = world["state"].positions()[SYM]
    assert SYM in world["broker"].positions()
    assert pos.stop_id in world["broker"].open_stop_ids(SYM)
    assert pos.stop < pos.entry  # long -> stop below entry
    order = world["broker"].s["stops"][pos.stop_id]
    assert order["side"] == "sell" and order["stop"] == pytest.approx(pos.stop)


def test_rule2_if_stop_cannot_be_placed_position_is_flattened(world, monkeypatch):
    eng = world["make_engine"]()
    eng.reconcile()

    def boom(*a, **k):
        raise ConnectionError("exchange down")

    monkeypatch.setattr(world["broker"], "place_stop", boom)
    eng.step(world["feed"].now())
    assert not world["broker"].positions()  # never left unprotected
    assert not world["state"].positions()
    reasons = [f["reason"] for f in world["state"].fills()]
    assert reasons == ["entry", "stop_failed_flatten"]
    assert any("flatten" in a for a in world["alerts"])


def test_exchange_stop_fills_when_price_gaps_through(world):
    eng, ts = _enter(world)
    d, feed = world["data"][SYM], world["feed"]
    nxt = d.index[d.index.get_loc(ts) + 1]
    d.loc[ts, "low"] = d.loc[ts, "open"] * 0.5  # crash during the candle that just ran
    feed.set_time(nxt)
    eng.monitor(nxt)
    assert not world["broker"].positions()
    assert not world["state"].positions()
    assert [f["reason"] for f in world["state"].fills()][-1] == "stop"


def test_rule5_realized_pnl_computed_when_broker_omits_it(world):
    from bot.broker.base import Fill

    eng, _ = _enter(world)
    pos = world["state"].positions()[SYM]
    exit_px = pos.entry * 1.01
    eng._record(Fill("2026-01-01T00:00:00+00:00", SYM, "sell", pos.contracts, exit_px, 0.1, 0.0, "model_flip", "x"))
    last = world["state"].fills()[-1]
    assert last["realized_pnl"] == pytest.approx((exit_px - pos.entry) * pos.contracts * 0.001)


def test_order_below_minimum_notional_is_refused_not_forced(world):
    from dataclasses import replace

    from bot.engine import Engine
    from tests.conftest import FixedModel

    cfg = replace(world["cfg"], min_order_inr=10_000_000.0)  # absurd minimum -> any order is too small
    eng = Engine(cfg, world["broker"], world["feed"], FixedModel(), world["state"], world["ledger"],
                 notify=world["alerts"].append)
    eng.reconcile()
    eng.step(world["feed"].now())
    assert not world["broker"].positions() and not world["state"].fills()


def _engine_with_venue(world, fn):
    from bot.engine import Engine
    from tests.conftest import FixedModel

    return Engine(world["cfg"], world["broker"], world["feed"], FixedModel(), world["state"],
                  world["ledger"], notify=world["alerts"].append, venue_price=fn)


def test_venue_guard_blocks_entry_on_price_mismatch_or_failure(world):
    px = world["feed"].last_price(SYM)
    for fn in (lambda s: px * 1.02, lambda s: (_ for _ in ()).throw(TimeoutError("down"))):
        eng = _engine_with_venue(world, fn)
        eng.reconcile()
        eng.step(world["feed"].now())
        assert not world["broker"].positions()  # fail-safe: no entry
    eng = _engine_with_venue(world, lambda s: px * 1.001)  # within 0.5% -> allowed
    eng.reconcile()
    eng.step(world["feed"].now())
    assert SYM in world["broker"].positions()


def test_rule3_orphan_exchange_position_is_flattened(world):
    _enter(world)
    fresh = State(world["tmp"] / "new.db")  # state.db lost -> exchange position is unknown
    from bot.engine import Engine
    from bot.ledger import Ledger
    from tests.conftest import FixedModel

    eng2 = Engine(world["cfg"], world["broker"], world["feed"], FixedModel(), fresh,
                  Ledger(world["tmp"] / "l2.csv", fresh), notify=world["alerts"].append)
    notes = eng2.reconcile()
    assert not world["broker"].positions()
    assert any("FLATTENED" in n for n in notes)
    assert not world["broker"].s["stops"]


def test_rule3_db_position_gone_from_exchange_is_cleaned(world):
    eng, _ = _enter(world)
    world["broker"].s["positions"].clear()  # stop filled while the bot was down
    world["broker"].s["stops"].clear()
    eng2 = world["make_engine"]()
    notes = eng2.reconcile()
    assert not world["state"].positions()
    assert any("removed" in n for n in notes)
    assert world["state"].fills()[-1]["reason"].startswith("reconcile_closed_offline")


def test_rule3_missing_exchange_stop_is_replaced_on_restart(world):
    eng, _ = _enter(world)
    old = world["state"].positions()[SYM].stop_id
    world["broker"].s["stops"].clear()  # stop vanished
    eng2 = world["make_engine"]()
    eng2.reconcile()
    new = world["state"].positions()[SYM].stop_id
    assert new != old and new in world["broker"].open_stop_ids(SYM)


def test_rule4_killswitch_flattens_halts_and_survives_restart(world):
    eng, ts = _enter(world)
    eng.ks.limit = 0.03  # mechanism test at 3%; the shipped default is now 1%
    assert world["broker"].positions()
    world["broker"].s["cash"] -= 25  # about -2.5%: must NOT trip
    eng.monitor(ts)
    assert world["broker"].positions() and not eng.ks.halted
    world["broker"].s["cash"] -= 15  # about -4%: trips
    eng.monitor(ts)
    assert not world["broker"].positions() and not world["broker"].s["stops"]
    assert eng.ks.halted and any("KILL-SWITCH" in a for a in world["alerts"])
    # next candle, same UTC day: no new entries even though the model screams "buy"
    d, feed = world["data"][SYM], world["feed"]
    nxt = d.index[d.index.get_loc(ts) + 1]
    feed.set_time(nxt)
    eng.step(nxt)
    assert not world["broker"].positions()
    # a restart on the same day must remember the halt
    eng2 = world["make_engine"]()
    assert eng2.ks.halted and eng2.ks.start_equity == pytest.approx(eng.ks.start_equity)


def test_weekly_limit_halts_entries_even_after_daily_rearms(world):
    eng, ts = _enter(world)
    eng.ks.limit = 0.5          # daily loose, so only the weekly switch can trip
    eng.ks_week.limit = 0.03
    world["broker"].s["cash"] -= 40  # about -4% in the week
    eng.monitor(ts)
    assert eng.ks_week.halted and not eng.ks.halted
    assert not world["broker"].positions() and any("weekly" in a for a in world["alerts"])
    eng.ks.roll("2099-01-01", eng.broker.equity())  # a new day re-arms only the daily switch
    assert eng.entries_halted
    eng2 = world["make_engine"]()
    assert eng2.ks_week.halted and eng2.entries_halted


def test_time_exit_after_horizon(world):
    eng, ts = _enter(world)
    d, feed = world["data"][SYM], world["feed"]
    i = d.index.get_loc(ts)
    px = d.loc[ts, "open"]
    d.loc[d.index[i:], ["open", "high", "low", "close"]] = px  # dead-flat market: only the clock can exit
    for k in range(1, world["cfg"].horizon + 1):
        feed.set_time(d.index[i + k])
        eng.monitor(d.index[i + k])
        eng.step(d.index[i + k])
    reasons = [f["reason"] for f in world["state"].fills()]
    assert "time_exit" in reasons


def test_rule5_every_fill_in_csv_and_sqlite(world):
    eng, ts = _enter(world)
    eng.flatten_all("manual")
    rows = list(csv.DictReader(open(world["tmp"] / "ledger.csv", encoding="utf-8")))
    fills = world["state"].fills()
    assert len(rows) == len(fills) == 2
    assert list(rows[0]) == ["timestamp", "pair", "side", "qty", "price", "fee", "realized_pnl",
                             "reason", "order_id"]
    assert rows[0]["side"] == "buy" and rows[1]["side"] == "sell"
    assert float(rows[0]["fee"]) > 0 and float(rows[1]["fee"]) > 0
    assert float(rows[1]["realized_pnl"]) == pytest.approx(fills[1]["realized_pnl"])


def test_env_overrides_cannot_loosen_policy(monkeypatch):
    from bot.config import Settings

    monkeypatch.setenv("RISK_PER_TRADE", "0.05")
    with pytest.raises(ValueError):
        Settings.from_env()
    monkeypatch.setenv("RISK_PER_TRADE", "0.0025")  # stricter is allowed
    assert Settings.from_env().risk_per_trade == 0.0025
    for k, v in (("MAX_POSITIONS", "10"), ("DAILY_LOSS_LIMIT", "0.10"), ("WEEKLY_LOSS_LIMIT", "1.0"),
                 ("MONTHLY_LOSS_LIMIT", "0")):
        monkeypatch.setenv(k, v)
        with pytest.raises(ValueError):
            Settings.from_env()
        monkeypatch.delenv(k)


def test_failed_killswitch_flatten_is_retried(world):
    eng, ts = _enter(world)
    eng.ks.limit = 0.03
    broker = world["broker"]
    real = broker.market_order

    def boom(*a, **k):
        raise RuntimeError("exchange down")

    broker.market_order = boom
    broker.s["cash"] -= 40  # about -4%: trips
    eng.monitor(ts)
    assert eng.ks.halted and broker.positions()  # flatten failed, position still open
    assert any("FAILED" in a for a in world["alerts"])
    broker.market_order = real
    eng.monitor(ts)  # next tick retries
    assert not broker.positions()


def test_single_instance_lock_blocks_second_bot(tmp_path, monkeypatch):
    from dataclasses import replace

    from bot import main as m
    from bot.config import Settings

    cfg = replace(Settings(mode="paper"))
    monkeypatch.setattr(type(cfg), "run_dir", property(lambda self: tmp_path), raising=True)
    first = m.single_instance(cfg)
    with pytest.raises(SystemExit):
        m.single_instance(cfg)
    first.close()
    m._LOCKS.remove(first)
    m.single_instance(cfg).close()  # free again after the first holder exits
