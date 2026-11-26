"""Deflated Sharpe ratio (Bailey & Lopez de Prado 2014): corrects a backtest Sharpe for the number of trials."""

import json

import numpy as np
import pandas as pd
import pytest

from bot.stats import count_lab_trials, deflated_sharpe, expected_max_sharpe, sharpe_stats


def test_paper_worked_example():
    # Paper's example: annual SR 2.5 over 1250 days, 100 trials with variance 0.5 (annual), skew -3, kurtosis 10.
    d = deflated_sharpe(sr=2.5 / np.sqrt(250), t=1250, skew=-3.0, kurt=10.0, var_sr=0.5 / 250, n_trials=100)
    assert d["dsr"] == pytest.approx(0.90, abs=0.005)


def test_more_trials_raise_the_bar_and_lower_the_dsr():
    kw = dict(sr=0.08, t=1000, skew=0.0, kurt=3.0, var_sr=0.001)
    assert expected_max_sharpe(0.001, 1000) > expected_max_sharpe(0.001, 10)
    assert deflated_sharpe(n_trials=1000, **kw)["dsr"] < deflated_sharpe(n_trials=10, **kw)["dsr"]


def test_one_trial_is_the_plain_probabilistic_sharpe():
    assert expected_max_sharpe(0.01, 1) == 0.0


def test_sharpe_stats_uses_non_excess_kurtosis():
    r = pd.Series(np.random.default_rng(0).normal(0.001, 0.01, 20000))
    s = sharpe_stats(r)
    assert s["t"] == 20000 and s["sr"] == pytest.approx(0.1, abs=0.02)
    assert s["kurt"] == pytest.approx(3.0, abs=0.15) and s["skew"] == pytest.approx(0.0, abs=0.1)


def test_count_lab_trials_counts_every_parameter_setting_in_every_lab_report(tmp_path):
    for tag, n_cand in (("lab_a", 2), ("lab_b", 1)):
        cands = {f"c{i}": {"param_variant_returns_pct": [1.0, 2.0, 3.0]} for i in range(n_cand)}
        (tmp_path / f"{tag}.json").write_text(json.dumps({"candidates": cands}))
    (tmp_path / "holdout_x.json").write_text(json.dumps({"candidates": {"c": {"param_variant_returns_pct": [1, 2, 3]}}}))
    assert count_lab_trials(tmp_path, extra=1) == 9 + 1   # holdout is a test, not a selection; +1 rejected ML model
