"""crypto-budget: same size as the bot, says which limit decided, refuses instead of over-risking, chains to crypto-risk."""

import hashlib
import json
import sqlite3
from dataclasses import replace

import pytest

from bot.budget import main, size
from bot.config import Settings
from bot.feeds import SPOT_STEP
from bot.riskcheck import EXIT_BLOCK, EXIT_PASS, Context, Order, evaluate
from bot.risk import position_units, stop_price, to_contracts

CFG = replace(Settings(), market="spot", allow_short=False, max_leverage=1.0, min_order_inr=100.0,
              taker_fee=0.001, maker_fee=0.001, slippage=0.0005, stop_slippage=0.001, stop_atr=2.0)
BTC = "BTC/USD:USD"
CLEAR = {"daily": False, "weekly": False, "monthly": False}


def ctx(equity=113.6, positions=None, halted=None, errors=None):
    return Context(equity, positions or {}, halted or dict(CLEAR), errors or [])


@pytest.mark.parametrize("atr", [0.01, 0.03, 0.06])
def test_same_size_as_the_bot(atr):
    px = 95_000.0
    st = stop_price(1, px, atr, CFG)
    b = size(BTC, px, st, ctx(), CFG)
    bot = to_contracts(position_units(113.6, px, atr, CFG), SPOT_STEP[BTC]) * SPOT_STEP[BTC]
    assert b.qty == pytest.approx(bot) and b.limits["bot_would_trade"] == pytest.approx(bot)
    assert b.decided_by == "risk_per_trade" and b.risk_verdict["decision"] == "PASS"


def test_rounds_down_to_lot_step_and_never_over_risks():
    b = size(BTC, 95_000.0, 93_000.0, ctx(), CFG)
    steps = b.qty / SPOT_STEP[BTC]
    assert abs(steps - round(steps)) < 1e-6
    assert b.usd["loss_at_stop_incl_costs"] <= b.usd["risk_budget"] + 1e-9


def test_says_which_limit_decided_tight_stop_hits_leverage():
    b = size(BTC, 95_000.0, 94_990.0, ctx(), CFG)  # 0.01% stop -> risk allows a huge size, cash/1x cap decides
    assert b.decided_by in ("max_leverage", "free_cash")
    assert b.limits["risk_per_trade"] > b.limits["max_leverage"]
    assert b.usd["notional"] <= 113.6 + 1e-9


def test_free_cash_counts_open_positions():
    pos = {"ETH/USD:USD": {"side": 1, "contracts": 0.03, "coins": 0.03, "entry": 3000.0, "stop": 2800.0}}  # $90 in use
    b = size(BTC, 95_000.0, 94_990.0, ctx(positions=pos), CFG)
    assert b.decided_by == "free_cash" and b.usd["notional"] <= 113.6 - 90 + 1e-9
    assert b.risk_verdict["decision"] == "PASS"


def test_far_stop_is_refused_not_shrunk_below_minimum():
    b = size(BTC, 95_000.0, 50_000.0, ctx(), CFG)  # 47% stop -> an order worth a few rupees
    assert b.qty == 0 and b.decided_by == "min_order" and b.risk_verdict["decision"] == "BLOCK"
    assert b.min_order["capital_needed_inr"] > 113.6 * CFG.usdt_inr  # says what capital it would take


def test_capital_needed_is_the_threshold():
    need = size(BTC, 95_000.0, 93_000.0, ctx(), CFG).min_order["capital_needed_usd"]
    assert size(BTC, 95_000.0, 93_000.0, ctx(equity=need * 1.05), CFG).min_order["met"]
    assert not size(BTC, 95_000.0, 93_000.0, ctx(equity=need * 0.9), CFG).min_order["met"]


def test_no_slot_refuses():
    pos = {s: {"side": 1, "contracts": 0.0001, "coins": 0.0001, "entry": 1.0, "stop": 0.9} for s in ("ETH/USD:USD", "SOL/USD:USD")}
    b = size(BTC, 95_000.0, 93_000.0, ctx(positions=pos), CFG)
    assert b.qty == 0 and b.decided_by == "open_slots"


def test_kill_switch_shows_in_the_chained_verdict():
    b = size(BTC, 95_000.0, 93_000.0, ctx(halted={**CLEAR, "weekly": True}), CFG)
    assert b.qty > 0 and b.risk_verdict["decision"] == "BLOCK"
    assert any("weekly" in r for r in b.risk_verdict["reasons"])


def test_short_stop_on_spot_is_blocked_by_the_chain():
    assert size(BTC, 95_000.0, 97_000.0, ctx(), CFG).risk_verdict["decision"] == "BLOCK"


@pytest.mark.parametrize("price,stop,equity,errors", [
    (float("nan"), 93_000.0, 113.6, []), (95_000.0, -1.0, 113.6, []), (95_000.0, 95_000.0, 113.6, []),
    (95_000.0, 93_000.0, float("nan"), []), (95_000.0, 93_000.0, 0.0, []),
    (95_000.0, 93_000.0, 113.6, ["state.db missing"]),
])
def test_bad_input_or_state_refuses(price, stop, equity, errors):
    b = size(BTC, price, stop, ctx(equity=equity, errors=errors), CFG)
    assert b.qty == 0 and b.refused and b.risk_verdict["decision"] == "BLOCK"


def test_inr_view_uses_the_bot_rate():
    b = size(BTC, 95_000.0, 93_000.0, ctx(), CFG)
    assert b.inr["notional"] == pytest.approx(b.usd["notional"] * CFG.usdt_inr, abs=0.01)


def test_risk_check_now_counts_open_exposure():
    pos = {"ETH/USD:USD": {"side": 1, "contracts": 0.03, "coins": 0.03, "entry": 3000.0, "stop": 2800.0}}  # $90 open
    v = evaluate(Order("BTC", "buy", 0.0005, 95_000.0, 94_990.0), ctx(positions=pos), CFG)  # $47.5 more
    assert "total_exposure" in {c["name"] for c in v.checks if not c["ok"]}


# ------------------------------------------------------------------ CLI: read-only on state, writes only a proposal
def make_state(tmp_path, cash=113.6):
    d = tmp_path / "state" / "paper"
    d.mkdir(parents=True)
    (d / "paper_exchange.json").write_text(json.dumps({"cash": cash, "positions": {}, "stops": {}}))
    con = sqlite3.connect(d / "state.db")
    con.executescript("CREATE TABLE positions (symbol TEXT PRIMARY KEY, side INTEGER, contracts REAL, entry REAL,"
                      " stop REAL, stop_id TEXT, opened_ts TEXT); CREATE TABLE kv (key TEXT PRIMARY KEY, value TEXT);")
    con.commit()
    con.close()
    return d


def _cli(monkeypatch, tmp_path, d):
    monkeypatch.setattr("bot.budget.Settings",
                        type("S", (), {"from_env": staticmethod(lambda: replace(CFG, mode="paper"))}))
    monkeypatch.setattr("bot.budget._run_dir", lambda cfg: d)
    monkeypatch.setattr("bot.budget.ROOT", tmp_path)


def test_cli_reads_state_only_and_writes_one_proposal(tmp_path, monkeypatch, capsys):
    d = make_state(tmp_path)
    _cli(monkeypatch, tmp_path, d)
    before = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in d.iterdir()}
    rc = main(["--symbol", "BTC", "--price", "95000", "--stop", "93000", "--json", "--write"])
    out = json.loads(capsys.readouterr().out)
    assert rc == EXIT_PASS and out["placed"] is False and out["risk_verdict"]["decision"] == "PASS"
    written = json.loads((tmp_path / "proposals" / "paper_order.json").read_text())
    assert written["qty"] == out["qty"] and written["placed"] is False
    assert before == {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in d.iterdir()}


def test_cli_refusal_writes_nothing(tmp_path, monkeypatch, capsys):
    _cli(monkeypatch, tmp_path, make_state(tmp_path))
    rc = main(["--symbol", "BTC", "--price", "95000", "--stop", "50000", "--write"])
    assert rc == EXIT_BLOCK and "REFUSED" in capsys.readouterr().out
    assert not (tmp_path / "proposals").exists()


def test_cli_unknown_symbol_and_bad_settings_block(tmp_path, monkeypatch, capsys):
    _cli(monkeypatch, tmp_path, make_state(tmp_path))
    assert main(["--symbol", "DOGE", "--price", "1", "--stop", "0.9"]) == EXIT_BLOCK

    def boom():
        raise ValueError("risk settings outside policy")
    monkeypatch.setattr("bot.budget.Settings", type("S", (), {"from_env": staticmethod(boom)}))
    assert main(["--symbol", "BTC", "--price", "1", "--stop", "0.9"]) == EXIT_BLOCK


def test_bot_mode_failure_blocks(tmp_path, monkeypatch, capsys):
    _cli(monkeypatch, tmp_path, make_state(tmp_path))

    def down(sym, cfg):
        raise ConnectionError("binance unreachable")
    monkeypatch.setattr("bot.budget.bot_price_and_stop", down)
    assert main(["--symbol", "BTC", "--bot"]) == EXIT_BLOCK
    assert "could not get" in capsys.readouterr().out


def test_budget_with_an_engine_style_open_position(tmp_path):
    from bot.riskcheck import load_context
    d = make_state(tmp_path, cash=5000.0)
    con = sqlite3.connect(d / "state.db")
    con.execute("INSERT INTO positions VALUES ('BTC/USD:USD', 1, 3000, 95000, 90000, 'P1', 't')")  # 0.03 BTC
    con.commit()
    con.close()
    b = size("ETH/USD:USD", 3000.0, 2850.0, load_context(d), CFG)
    assert b.qty > 0 and b.risk_verdict["decision"] == "PASS"
    assert b.usd["free_cash"] == pytest.approx(4850.0 - 2850.0)


def test_refused_write_removes_an_old_proposal(tmp_path, monkeypatch, capsys):
    _cli(monkeypatch, tmp_path, make_state(tmp_path))
    assert main(["--symbol", "BTC", "--price", "95000", "--stop", "93000", "--write"]) == EXIT_PASS
    assert (tmp_path / "proposals" / "paper_order.json").exists()
    assert main(["--symbol", "BTC", "--price", "95000", "--stop", "50000", "--write"]) == EXIT_BLOCK
    assert not (tmp_path / "proposals" / "paper_order.json").exists()
    assert "removed old proposal" in capsys.readouterr().out


def test_bot_flag_with_manual_price_is_a_usage_error(tmp_path, monkeypatch):
    _cli(monkeypatch, tmp_path, make_state(tmp_path))
    with pytest.raises(SystemExit) as e:
        main(["--symbol", "BTC", "--bot", "--price", "1"])
    assert e.value.code == 2


def test_zero_stop_atr_refuses_instead_of_crashing():
    b = size(BTC, 95_000.0, 93_000.0, ctx(), replace(CFG, stop_atr=0.0))
    assert b.qty == 0 and b.risk_verdict["decision"] == "BLOCK"


def test_json_output_has_no_bare_nan(tmp_path, monkeypatch, capsys):
    _cli(monkeypatch, tmp_path, make_state(tmp_path))
    main(["--symbol", "BTC", "--price", "nan", "--stop", "93000", "--json"])
    out = capsys.readouterr().out
    assert "NaN" not in out and "Infinity" not in out
    json.loads(out)


def test_bot_mode_stale_candles_block(monkeypatch):
    import pandas as pd

    from bot import budget

    class Feed:
        def __init__(self, cfg): pass
        def now(self): return pd.Timestamp("2026-11-25 12:07", tz="UTC")
        def ohlcv_closed(self, sym, n):
            idx = pd.date_range(end="2026-11-25 09:00", periods=400, freq="15min", tz="UTC")  # 3 hours old
            return pd.DataFrame({"open": 1.0, "high": 1.0, "low": 1.0, "close": 1.0, "volume": 1.0}, index=idx)
        def last_price(self, sym): return 1.0

    monkeypatch.setattr("bot.feeds.LiveFeed", Feed)
    monkeypatch.setattr("bot.main.get_model", lambda cfg: type("M", (), {"lookback": 600, "min_candles": 300})())
    with pytest.raises(RuntimeError, match="stale"):
        budget.bot_price_and_stop(BTC, CFG)


@pytest.mark.parametrize("args", [["--symbol", "DOGE", "--price", "1", "--stop", "0.9", "--write"],
                                  ["--symbol", "BTC", "--bot", "--write"]])
def test_early_refusals_also_remove_an_old_proposal(tmp_path, monkeypatch, capsys, args):
    _cli(monkeypatch, tmp_path, make_state(tmp_path))
    assert main(["--symbol", "BTC", "--price", "95000", "--stop", "93000", "--write"]) == EXIT_PASS

    def down(sym, cfg):
        raise ConnectionError("binance unreachable")
    monkeypatch.setattr("bot.budget.bot_price_and_stop", down)
    assert main(args) == EXIT_BLOCK
    assert not (tmp_path / "proposals" / "paper_order.json").exists()


def test_failure_inside_the_fallback_still_refuses(monkeypatch):
    def broken(*a, **k):
        raise RuntimeError("boom")
    monkeypatch.setattr("bot.budget._size", broken)
    monkeypatch.setattr("bot.budget._done", broken)
    b = size(BTC, 95_000.0, 93_000.0, ctx(), CFG)
    assert b.qty == 0 and b.risk_verdict["decision"] == "BLOCK"
