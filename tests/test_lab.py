import pandas as pd
import pytest

from bot.lab import CANDIDATES, _from_state, gate, monte_carlo
from tests.conftest import make_candles


@pytest.mark.parametrize("name", list(CANDIDATES))
def test_rule1_every_candidate_is_free_of_lookahead(name):
    fn, params, _, daily = CANDIDATES[name]
    p = min(params)  # smallest warm-up
    df = make_candles(2500, drift=0.0003)
    t = 1800
    df2 = df.copy()
    df2.iloc[t:, :4] *= 0.6
    f1, f2 = _from_state(df, fn(df, p), daily), _from_state(df2, fn(df2, p), daily)
    pd.testing.assert_frame_equal(f1.iloc[: t + 1], f2.iloc[: t + 1])


def test_ensemble_model_matches_lab_candidate_and_trades_in_engine(world):
    from bot.lab import EnsembleModel, state_ensemble
    from tests.conftest import SYM

    df = make_candles(1500, drift=0.0008, vol=0.0005)
    m = EnsembleModel(days=1)
    pd.testing.assert_frame_equal(m.frame(df), _from_state(df, state_ensemble(df, 1), True))
    world["data"][SYM] = df
    world["feed"].data = world["data"]
    world["feed"].set_time(df.index[1200])
    eng = world["make_engine"](m)
    eng.reconcile()
    eng.step(world["feed"].now())
    pos = world["state"].positions()[SYM]
    assert pos.side == 1 and pos.stop_id in world["broker"].open_stop_ids(SYM)


def test_monte_carlo_separates_edge_from_noise():
    good = monte_carlo([2.0] * 60 + [-1.0] * 40, 1000.0)
    bad = monte_carlo([1.0] * 40 + [-1.5] * 60, 1000.0)
    assert good["p_loss"] < 0.05 and bad["p_loss"] > 0.95
    assert monte_carlo([1.0] * 3, 1000.0)["p_loss"] == 1.0  # too few trades -> never promote


def test_gate_requires_every_condition():
    full = {"return_pct": 20.0, "profit_factor": 1.4}
    mc_ok = {"p_loss": 0.1}
    assert gate(full, [5, 3, -1, 8], [10, 20, 5], mc_ok)[0]
    assert not gate(full, [5, -3, -1, 8], [10, 20, 5], mc_ok)[0]  # only 2/4 sub-periods
    assert not gate(full, [5, 3, 1, 8], [10, -20, -5], mc_ok)[0]  # fragile to parameters
    assert not gate(full, [5, 3, 1, 8], [10, 20, 5], {"p_loss": 0.4})[0]
    assert not gate({"return_pct": 5.0, "profit_factor": 1.05}, [5, 3, 1, 8], [10, 20, 5], mc_ok)[0]
