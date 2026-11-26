"""crypto-risk: every policy limit blocks, unreadable state blocks, and the check never writes."""

import hashlib
import json
import sqlite3
from dataclasses import replace

import pytest

from bot.config import Settings
from bot.riskcheck import EXIT_BLOCK, EXIT_PASS, Context, Order, evaluate, load_context, main, round_trip_cost_pct

CFG = replace(Settings(), market="spot", allow_short=False, max_leverage=1.0, min_order_inr=100.0,
              taker_fee=0.001, slippage=0.0005, stop_slippage=0.001)
CLEAR = {"daily": False, "weekly": False, "monthly": False}


def ctx(equity=1000.0, positions=None, halted=None, errors=None):
    return Context(equity, positions or {}, halted or dict(CLEAR), errors or [])


def ok_order(**kw):
    base = dict(symbol="BTC", side="buy", qty=0.002, price=100_000.0, stop=98_000.0)
    base.update(kw)
    return Order(**base)


def failed(v):
    return {c["name"] for c in v.checks if not c["ok"]}


def test_good_order_passes_and_reports_numbers():
    v = evaluate(ok_order(), ctx(), CFG)
    assert v.decision == "PASS", v.reasons
    # loss at stop = 0.002 * (2000 + 100000 * cost)
    exp = 0.002 * (2000 + 100_000 * round_trip_cost_pct(CFG))
    assert v.numbers["risk"] == pytest.approx(exp, rel=1e-6)
    assert v.numbers["risk"] <= 1000 * CFG.risk_per_trade


def test_risk_over_budget_blocks_and_says_which_limit():
    v = evaluate(ok_order(qty=0.01), ctx(), CFG)
    assert v.decision == "BLOCK" and "risk_per_trade" in failed(v)
    assert v.numbers["binding_limit"] == "risk_per_trade" and v.numbers["max_qty"] < 0.01


def test_costs_are_counted_in_risk():
    # stop distance alone fits the budget exactly; fees + slippage push it over
    qty = 1000 * CFG.risk_per_trade / 2000
    v = evaluate(ok_order(qty=qty), ctx(), CFG)
    assert "risk_per_trade" in failed(v)


def test_leverage_cap_blocks():
    # tight stop makes risk tiny, but notional 2x equity breaks the 1x spot cap
    v = evaluate(ok_order(qty=0.02, stop=99_990.0), ctx(), CFG)
    assert "max_leverage" in failed(v)


def test_no_stop_blocks():
    assert "stop_given" in failed(evaluate(ok_order(stop=None), ctx(), CFG))


def test_stop_on_wrong_side_blocks():
    assert "stop_on_protective_side" in failed(evaluate(ok_order(stop=101_000.0), ctx(), CFG))


def test_short_blocked_on_spot():
    v = evaluate(ok_order(side="sell", stop=102_000.0), ctx(), CFG)
    assert "shorting_allowed" in failed(v)


@pytest.mark.parametrize("which", ["daily", "weekly", "monthly"])
def test_any_kill_switch_blocks_entries(which):
    v = evaluate(ok_order(), ctx(halted={**CLEAR, which: True}), CFG)
    assert "kill_switch_clear" in failed(v) and which in " ".join(v.reasons)


def test_exit_allowed_while_halted():
    pos = {"BTC/USD:USD": {"side": 1, "contracts": 0.002, "coins": 0.002, "entry": 99_000.0, "stop": 97_000.0}}
    v = evaluate(ok_order(side="sell", stop=None), ctx(positions=pos, halted={**CLEAR, "daily": True}), CFG)
    assert v.decision == "PASS" and v.numbers["kind"] == "exit"


def test_exit_larger_than_position_blocks():
    pos = {"BTC/USD:USD": {"side": 1, "contracts": 0.001, "coins": 0.001, "entry": 99_000.0, "stop": 97_000.0}}
    v = evaluate(ok_order(side="sell", qty=0.002, stop=None), ctx(positions=pos), CFG)
    assert "exit_not_larger_than_position" in failed(v)


def test_max_positions_and_duplicate_block():
    pos = {s: {"side": 1, "contracts": 1, "coins": 1, "entry": 1, "stop": 0.9} for s in ("ETH/USD:USD", "SOL/USD:USD")}
    assert "max_positions" in failed(evaluate(ok_order(), ctx(positions=pos), CFG))
    one = {"BTC/USD:USD": {"side": 1, "contracts": 1, "coins": 1, "entry": 1, "stop": 0.9}}
    assert "not_already_held" in failed(evaluate(ok_order(), ctx(positions=one), CFG))


def test_below_minimum_order_blocks():
    v = evaluate(ok_order(qty=0.00001), ctx(), CFG)  # $1 = Rs 88 < Rs 100
    assert "min_order" in failed(v)


def test_unknown_symbol_blocks():
    assert "symbol_traded" in failed(evaluate(ok_order(symbol="DOGE"), ctx(), CFG))


@pytest.mark.parametrize("field,val", [("price", float("nan")), ("price", -1.0), ("qty", 0.0),
                                       ("qty", float("inf")), ("side", "hold")])
def test_bad_inputs_block(field, val):
    assert evaluate(ok_order(**{field: val}), ctx(), CFG).decision == "BLOCK"


def test_unreadable_state_blocks_even_a_good_order():
    v = evaluate(ok_order(), ctx(errors=["state.db missing"]), CFG)
    assert v.decision == "BLOCK" and "state_readable" in failed(v)


def test_bad_equity_blocks():
    assert "equity_positive" in failed(evaluate(ok_order(), ctx(equity=float("nan")), CFG))


def test_sizing_mode_returns_max_qty_that_passes():
    v = evaluate(ok_order(qty=None), ctx(), CFG)
    assert v.decision == "PASS" and v.numbers["sized_for_you"]
    again = evaluate(ok_order(qty=v.numbers["max_qty"]), ctx(), CFG)
    assert again.decision == "PASS"


# ------------------------------------------------------------------ state reading + CLI
def make_state(tmp_path, cash=1000.0, halted=False, positions=()):
    d = tmp_path / "state" / "paper"
    d.mkdir(parents=True)
    (d / "paper_exchange.json").write_text(json.dumps({"cash": cash, "positions": {}, "stops": {}}))
    con = sqlite3.connect(d / "state.db")
    con.executescript("CREATE TABLE positions (symbol TEXT PRIMARY KEY, side INTEGER, contracts REAL, "
                      "entry REAL, stop REAL, stop_id TEXT, opened_ts TEXT);"
                      "CREATE TABLE kv (key TEXT PRIMARY KEY, value TEXT);")
    con.execute("INSERT INTO kv VALUES ('ks_halted', ?)", ("1" if halted else "0",))
    for p in positions:
        con.execute("INSERT INTO positions VALUES (?,?,?,?,?,?,?)", p)
    con.commit()
    con.close()
    return d


def test_load_context_reads_halt_and_positions(tmp_path):
    d = make_state(tmp_path, halted=True, positions=[("ETH/USD:USD", 1, 0.1, 3000, 2900, "P1", "t")])
    c = load_context(d)
    assert c.equity == pytest.approx(1000.0 + (2900 - 3000) * 0.1 * 0.0001) and c.halted["daily"]  # ETH at its stop and "ETH/USD:USD" in c.positions and not c.errors


def test_load_context_missing_and_corrupt_fail_closed(tmp_path):
    assert load_context(tmp_path / "nowhere").errors
    d = make_state(tmp_path)
    (d / "state.db").write_bytes(b"not a database")
    assert any("state.db" in e for e in load_context(d).errors)


def test_cli_never_writes_state(tmp_path, monkeypatch, capsys):
    d = make_state(tmp_path)
    before = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in d.iterdir()}
    monkeypatch.setattr("bot.riskcheck.Settings", type("S", (), {"from_env": staticmethod(
        lambda: replace(CFG, mode="paper"))}))
    monkeypatch.setattr("bot.riskcheck._run_dir", lambda cfg: d)
    rc = main(["--symbol", "BTC", "--side", "buy", "--qty", "0.002", "--price", "100000", "--stop", "98000"])
    assert rc == EXIT_PASS and capsys.readouterr().out.startswith("PASS")
    rc = main(["--symbol", "BTC", "--side", "buy", "--qty", "1", "--price", "100000", "--stop", "98000", "--json"])
    assert rc == EXIT_BLOCK and json.loads(capsys.readouterr().out)["decision"] == "BLOCK"
    after = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in d.iterdir()}
    assert before == after


# ------------------------------------------------------------------ review findings (silent-failure-hunter)
LONG = {"BTC/USD:USD": {"side": 1, "contracts": 0.002, "coins": 0.002, "entry": 99_000.0, "stop": 97_000.0}}


def test_exit_without_qty_blocks():
    assert "exit_qty_given" in failed(evaluate(ok_order(side="sell", qty=None, stop=None), ctx(positions=LONG), CFG))


def test_short_cover_is_an_exit():
    short = {"BTC/USD:USD": {"side": -1, "contracts": 0.002, "coins": 0.002, "entry": 99_000.0, "stop": 101_000.0}}
    v = evaluate(ok_order(side="buy", stop=None), ctx(positions=short), CFG)
    assert v.decision == "PASS" and v.numbers["kind"] == "exit"


@pytest.mark.parametrize("sym", ["BTC/INR", "BTC/ETH", "btc:xyz", "", "/USDT", "BTC/USD:INR"])
def test_other_markets_do_not_match(sym):
    assert "symbol_traded" in failed(evaluate(ok_order(symbol=sym), ctx(), CFG))


@pytest.mark.parametrize("stop", [float("nan"), float("inf"), -1.0])
def test_bad_stop_blocks(stop):
    assert evaluate(ok_order(stop=stop), ctx(), CFG).decision == "BLOCK"


@pytest.mark.parametrize("val", ["true", " 1", "", "2"])
def test_garbled_kill_switch_value_blocks(tmp_path, val):
    d = make_state(tmp_path)
    con = sqlite3.connect(d / "state.db")
    con.execute("UPDATE kv SET value=? WHERE key='ks_halted'", (val,))
    con.commit()
    con.close()
    c = load_context(d)
    assert c.errors and c.halted["daily"]
    assert evaluate(ok_order(), c, CFG).decision == "BLOCK"


def test_invalid_position_side_blocks(tmp_path):
    d = make_state(tmp_path, positions=[("ETH/USD:USD", 0, 0.1, 3000, 2900, "P1", "t")])
    assert any("invalid side" in e for e in load_context(d).errors)


def _cli(monkeypatch, d, settings=None):
    monkeypatch.setattr("bot.riskcheck.Settings", type("S", (), {"from_env": staticmethod(
        settings or (lambda: replace(CFG, mode="paper")))}))
    monkeypatch.setattr("bot.riskcheck._run_dir", lambda cfg: d)


def test_equity_override_cannot_raise_limits(tmp_path, monkeypatch, capsys):
    _cli(monkeypatch, make_state(tmp_path, cash=1000.0))
    args = ["--symbol", "BTC", "--side", "buy", "--qty", "5", "--price", "100000", "--stop", "99000", "--json"]
    assert main(args + ["--equity", "1000000"]) == EXIT_BLOCK
    assert "refused" in json.dumps(json.loads(capsys.readouterr().out)["reasons"])
    assert main(["--symbol", "BTC", "--side", "buy", "--price", "100000", "--stop", "98000", "--equity", "500",
                 "--json"]) == EXIT_PASS
    assert json.loads(capsys.readouterr().out)["numbers"]["equity_override"] == 500


def test_bad_settings_block_with_block_exit_code(tmp_path, monkeypatch, capsys):
    def boom():
        raise ValueError("risk settings outside policy")
    _cli(monkeypatch, make_state(tmp_path), boom)
    assert main(["--symbol", "BTC", "--side", "buy", "--price", "1", "--stop", "0.9"]) == EXIT_BLOCK
    assert capsys.readouterr().out.startswith("BLOCK")


def test_engine_units_are_converted_to_coins(tmp_path):
    """The engine stores spot size as a count of lot steps: 3000 BTC steps = 0.03 BTC."""
    d = make_state(tmp_path, cash=5000.0, positions=[("BTC/USD:USD", 1, 3000, 95_000.0, 90_000.0, "P1", "t")])
    c = load_context(d)
    assert c.positions["BTC/USD:USD"]["coins"] == pytest.approx(0.03)
    assert c.equity == pytest.approx(5000.0 - 5000 * 0.03)  # worst case: the stop fills
    assert evaluate(ok_order(side="sell", qty=0.03, stop=None), c, CFG).decision == "PASS"
    assert "exit_not_larger_than_position" in failed(evaluate(ok_order(side="sell", qty=0.04, stop=None), c, CFG))
    v = evaluate(Order("ETH", "buy", 0.1, 3000.0, 2900.0), c, CFG)  # $300 more; open BTC is $2,850, not $285M
    assert "total_exposure" not in failed(v)
