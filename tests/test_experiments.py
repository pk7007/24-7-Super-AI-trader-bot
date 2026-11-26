"""Champion-challenger log: every lab challenger gets a logged promote/reject decision; nothing changes production."""

from bot.experiments import decide, has_decision, write_log


def cand(ret, pf, promote=True, why=()):
    return {"promote": promote, "rejected_because": list(why), "main_param": 14,
            "full": {"return_pct": ret, "profit_factor": pf, "trades": 50, "max_drawdown_pct": -5.0}}


BASE = {"window": "2023 -> 2026", "taker_fee": 0.001,
        "candidates": {"ensemble": cand(20, 2.5), "donchian": cand(30, 2.8), "tsmom": cand(5, 1.1, False, ["weak"]),
                       "trend_ema": cand(10, 1.6)}}
STRESS = {"taker_fee": 0.005, "candidates": {"ensemble": cand(15, 2.1), "donchian": cand(12, 1.9), "trend_ema": cand(2, 1.1, False, ["weak"])}}
HOLDOUT = {"window": "2021 -> 2023", "candidates": {"ensemble": cand(5.3, 1.87)}}


def test_failing_gate_is_rejected_with_its_reason():
    d = {x["challenger"]: x for x in decide(BASE, STRESS, HOLDOUT, champion="ensemble")}
    assert d["tsmom"]["decision"] == "reject" and any("lab gate" in r for r in d["tsmom"]["reasons"])


def test_challenger_must_beat_champion_at_both_fee_levels():
    d = {x["challenger"]: x for x in decide(BASE, STRESS, HOLDOUT, champion="ensemble")}
    assert d["donchian"]["decision"] == "reject"          # beats at 0.10% but loses at 0.50% fees
    assert any("0.50%" in r for r in d["donchian"]["reasons"])
    assert d["trend_ema"]["decision"] == "reject"


def test_no_promotion_without_its_own_holdout():
    stress = {"taker_fee": 0.005, "candidates": {**STRESS["candidates"], "donchian": cand(25, 2.4)}}
    d = {x["challenger"]: x for x in decide(BASE, stress, HOLDOUT, champion="ensemble")}
    assert d["donchian"]["decision"] == "reject" and any("holdout" in r for r in d["donchian"]["reasons"])


def test_a_challenger_that_clears_everything_is_only_proposed_never_switched():
    stress = {"taker_fee": 0.005, "candidates": {**STRESS["candidates"], "donchian": cand(25, 2.4)}}
    holdout = {"window": "h", "candidates": {**HOLDOUT["candidates"], "donchian": cand(9, 2.0)}}
    d = {x["challenger"]: x for x in decide(BASE, stress, holdout, champion="ensemble")}
    assert d["donchian"]["decision"] == "propose: 30 days in shadow, then your approval"


def test_log_records_champion_holdout_and_trial_count(tmp_path):
    p = tmp_path / "experiments.md"
    assert not has_decision(p)
    write_log(decide(BASE, STRESS, HOLDOUT, champion="ensemble"), p, champion="ensemble", base=BASE, stress=STRESS,
              holdout=HOLDOUT, n_trials=97)
    text = p.read_text(encoding="utf-8")
    assert "97 trials" in text and "holdout" in text and "| tsmom | reject |" in text
    assert has_decision(p)
