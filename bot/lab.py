"""Strategy lab: test candidate strategies under identical costs and promote only the robust ones.

Ideas borrowed from the reference repos:
  freqtrade / jesse  - several strategy families, walk-forward style evaluation, same cost model
  day-trader-skill   - "Time Machine": resample trade outcomes thousands of times for honest odds
  OctoBot            - evaluators that vote (here: the ensemble candidate)

A candidate is promoted ONLY if it passes every gate (see ``gate``). Nothing here trades.
All signals are shifted by one candle (RULE 1) via ``_from_state``.
"""

from __future__ import annotations

import json
from dataclasses import replace

import numpy as np
import pandas as pd

from .backtest import simulate
from .config import ROOT, Settings
from .features import atr
from .stats import count_lab_trials, deflated_sharpe, sharpe_stats

BPD = 96  # 15-minute bars per day


def _from_state(df: pd.DataFrame, state: pd.Series, daily_scale: bool = True) -> pd.DataFrame:
    out = pd.DataFrame(0.05, index=df.index, columns=["p_down", "p_flat", "p_up"])
    out.loc[state > 0, "p_up"] = 0.9
    out.loc[state < 0, "p_down"] = 0.9
    a = atr(df, BPD * 14) / df["close"] * np.sqrt(BPD) if daily_scale else atr(df) / df["close"]
    out["atr_pct"] = a
    return out.shift(1)


def state_trend(df, days):
    ema = df["close"].ewm(span=days * BPD, adjust=False).mean()
    slope = ema - ema.shift(BPD)
    return pd.Series(np.where((df["close"] > ema) & (slope > 0), 1, np.where((df["close"] < ema) & (slope < 0), -1, 0)),
                     index=df.index)


def state_tsmom(df, days):
    return np.sign(df["close"] / df["close"].shift(days * BPD) - 1).fillna(0)


def state_donchian(df, days):
    n = days * BPD
    hh, ll = df["high"].rolling(n).max().shift(1), df["low"].rolling(n).min().shift(1)
    raw = pd.Series(np.where(df["close"] > hh, 1, np.where(df["close"] < ll, -1, 0)), index=df.index)
    return raw.replace(0, np.nan).ffill().fillna(0)  # stay in the last breakout direction


def state_ensemble(df, days):
    a, b = state_trend(df, days), state_tsmom(df, days * 2)
    return a.where(a == b, 0)


def state_meanrev(df, thr):
    d = df["close"].diff()
    up = d.clip(lower=0).ewm(alpha=1 / 14, adjust=False).mean()
    dn = (-d.clip(upper=0)).ewm(alpha=1 / 14, adjust=False).mean()
    rsi = (100 - 100 / (1 + up / dn.replace(0, np.nan))).fillna(50).to_numpy()
    s, cur = np.zeros(len(rsi)), 0
    for i, r in enumerate(rsi):
        if cur == 0:
            cur = 1 if r < thr else (-1 if r > 100 - thr else 0)
        elif (cur == 1 and r > 50) or (cur == -1 and r < 50):
            cur = 0
        s[i] = cur
    return pd.Series(s, index=df.index)


SLOW = dict(horizon=BPD * 90, stop_atr=2.0, tp_atr=1000.0, risk_per_trade=0.01, max_leverage=2.0, max_positions=3)
FAST = dict(horizon=32, stop_atr=2.0, tp_atr=2.0, risk_per_trade=0.005, max_leverage=2.0, max_positions=3)

# name -> (state fn, parameter variants (middle one is the "main" setting), config overrides, daily-scale ATR?)
CANDIDATES = {
    "trend_ema":   (state_trend,    [10, 14, 21], SLOW, True),
    "donchian":    (state_donchian, [10, 20, 40], SLOW, True),
    "tsmom":       (state_tsmom,    [14, 30, 60], SLOW, True),
    "ensemble":    (state_ensemble, [10, 14, 21], SLOW, True),
    "meanrev_rsi": (state_meanrev,  [20, 25, 30], FAST, False),
}


class EnsembleModel:
    """Production wrapper for the 'ensemble' candidate: trade only when the EMA-trend rule and the
    2x-longer time-series-momentum rule agree. Same interface as TrendModel."""

    def __init__(self, days: int = 14):
        self.days = days
        self.min_candles = max(3 * days * BPD, 288)
        self.lookback = self.min_candles + 3 * BPD

    def frame(self, df: pd.DataFrame) -> pd.DataFrame:
        return _from_state(df, state_ensemble(df, self.days), True)

    def predict_from_candles(self, ext: pd.DataFrame):
        if len(ext) < self.min_candles:
            return None
        row = self.frame(ext).iloc[-1]
        return row[["p_down", "p_flat", "p_up"]], float(row["atr_pct"])


def frames(df_by_sym, fn, p, daily):
    return {s: _from_state(d, fn(d, p), daily) for s, d in df_by_sym.items()}


def run_one(cfg, data, fn, p, daily, start, end):
    fr = frames(data, fn, p, daily)
    feats = {s: f[["atr_pct"]] for s, f in fr.items()}
    probs = {s: f[["p_down", "p_flat", "p_up"]] for s, f in fr.items()}
    return simulate(cfg, data, feats, probs, start, end)


def monte_carlo(pnls: list[float], start_equity: float, n_sims: int = 3000, seed: int = 11) -> dict:
    """'Time Machine': resample the realised trade PnLs (with replacement) to see the spread of outcomes."""
    if len(pnls) < 10:
        return {"p_loss": 1.0, "median_ret_pct": 0.0, "p5_ret_pct": 0.0, "p95_dd_pct": 100.0}
    rng = np.random.default_rng(seed)
    arr = np.array(pnls)
    paths = start_equity + np.cumsum(rng.choice(arr, size=(n_sims, len(arr)), replace=True), axis=1)
    final = paths[:, -1]
    peak = np.maximum.accumulate(paths, axis=1)
    dd = ((paths - peak) / peak).min(axis=1)
    return {"p_loss": float((final < start_equity).mean()),
            "median_ret_pct": float(np.median(final) / start_equity * 100 - 100),
            "p5_ret_pct": float(np.percentile(final, 5) / start_equity * 100 - 100),
            "p95_dd_pct": float(-np.percentile(dd, 5) * 100)}


def gate(full_main: dict, windows: list[float], variants: list[float], mc: dict) -> tuple[bool, list[str]]:
    why = []
    if not (full_main["return_pct"] > 0 and (full_main["profit_factor"] or 0) >= 1.2):
        why.append(f"full-period weak (ret {full_main['return_pct']}%, PF {full_main['profit_factor']})")
    if sum(w > 0 for w in windows) < 3:
        why.append(f"profitable in only {sum(w > 0 for w in windows)}/4 sub-periods")
    if mc["p_loss"] > 0.25:
        why.append(f"resampled P(loss) {mc['p_loss']:.0%} > 25%")
    if sum(v > 0 for v in variants) < 2:
        why.append(f"only {sum(v > 0 for v in variants)}/3 parameter settings profitable")
    return (not why), why


def _deflate(report: dict, trials: dict, reports_dir, tag: str) -> None:
    """Add a deflated Sharpe ratio to every candidate's main setting (bot/stats.py). The trial count covers every
    setting in every earlier lab report plus this run and the rejected LightGBM model, so it is conservative."""
    if not trials:
        return
    srs = [sharpe_stats(r)["sr"] for r in trials.values()]
    var_sr = float(np.var(srs, ddof=1)) if len(srs) > 1 else 0.0
    n = count_lab_trials(reports_dir, extra=1, skip=tag) + len(trials)
    for name, c in report["candidates"].items():
        r = trials.get((name, c["main_param"]))
        if r is None:
            continue
        s = sharpe_stats(r)
        d = deflated_sharpe(s["sr"], s["t"], s["skew"], s["kurt"], var_sr, n)
        # Sensitivity: Sharpe variance within the candidate's own family (daily-scale trend rules vs intraday
        # mean reversion, fixed by design in CANDIDATES). The headline above stays the all-trials number.
        fam = [sharpe_stats(t)["sr"] for (nm, _), t in trials.items() if CANDIDATES[nm][3] == CANDIDATES[name][3]]
        df_ = deflated_sharpe(s["sr"], s["t"], s["skew"], s["kurt"], float(np.var(fam, ddof=1)) if len(fam) > 1 else 0.0, n)
        c["deflated_sharpe"] = {"dsr": round(d["dsr"], 3), "passes_0_95": d["dsr"] >= 0.95,
                                "sharpe_annual": round(s["sr"] * np.sqrt(365), 2),
                                "benchmark_sharpe_annual": round(d["sr0"] * np.sqrt(365), 2),
                                "n_trials": n, "days": s["t"], "skew": round(s["skew"], 2), "kurtosis": round(s["kurt"], 2),
                                "same_family_dsr": round(df_["dsr"], 3),
                                "same_family_benchmark_sharpe_annual": round(df_["sr0"] * np.sqrt(365), 2)}
        print(f"{name:12s} deflated Sharpe {d['dsr']:.3f} (Sharpe {s['sr'] * np.sqrt(365):.2f}/yr vs "
              f"{d['sr0'] * np.sqrt(365):.2f}/yr expected from the best of {n} skill-less trials); same family "
              f"{df_['dsr']:.3f} (bar {df_['sr0'] * np.sqrt(365):.2f}/yr)", flush=True)


def run_lab(cfg: Settings, data: dict[str, pd.DataFrame], warmup_days: int = 95,
            only: list[str] | None = None, tag: str = "lab") -> dict:
    first = max(d.index[0] for d in data.values())
    last = min(d.index[-1] for d in data.values()) + pd.Timedelta(minutes=cfg.tf_minutes)
    start = first + pd.Timedelta(days=warmup_days)
    edges = pd.date_range(start, last, periods=5)
    report = {"window": f"{start.date()} -> {last.date()}", "market": cfg.market, "allow_short": cfg.allow_short,
              "max_leverage": cfg.max_leverage, "taker_fee": cfg.taker_fee, "gst": cfg.gst,
              "slippage": cfg.slippage, "candidates": {}}
    trials: dict[tuple[str, int], pd.Series] = {}  # daily returns of every (candidate, parameter) run
    for name, (fn, params, over, daily) in CANDIDATES.items():
        if only and name not in only:
            continue
        # keep the market profile's leverage cap: strategy overrides must never raise leverage
        c = replace(cfg, **{**over, "max_leverage": min(over.get("max_leverage", 99), cfg.max_leverage),
                            "risk_per_trade": min(over.get("risk_per_trade", 9), cfg.risk_per_trade),
                            "max_positions": min(over.get("max_positions", 99), cfg.max_positions)})
        main_p = params[1]
        variants, full_main = [], None
        for p in params:
            r = run_one(c, data, fn, p, daily, start, last)
            variants.append(r.metrics.get("return_pct", -100.0))
            trials[(name, p)] = r.curve.resample("1D").last().dropna().pct_change().dropna()
            if p == main_p:
                full_main, full_res = r.metrics, r
        windows = [run_one(c, data, fn, main_p, daily, edges[i], edges[i + 1]).metrics.get("return_pct", 0.0)
                   for i in range(4)]
        mc = monte_carlo([t.pnl for t in full_res.trades], cfg.start_equity)
        ok, why = gate(full_main, windows, variants, mc)
        report["candidates"][name] = {
            "effective_config": {k: getattr(c, k) for k in (
                "risk_per_trade", "max_positions", "max_leverage", "daily_loss_limit", "weekly_loss_limit",
                "monthly_loss_limit", "stop_atr", "taker_fee", "maker_fee", "gst", "slippage", "stop_slippage",
                "allow_short", "market")},
            "main_param": main_p, "full": {k: full_main[k] for k in ("return_pct", "max_drawdown_pct", "profit_factor",
                                                                      "trades", "win_rate_pct", "fees_paid_usd")},
            "subperiod_returns_pct": [round(w, 1) for w in windows],
            "param_variant_returns_pct": [round(v, 1) for v in variants],
            "monte_carlo": {k: round(v, 3) for k, v in mc.items()},
            "promote": ok, "rejected_because": why,
        }
        print(f"{name:12s} main={main_p:>3}  ret {full_main['return_pct']:+7.1f}%  dd {full_main['max_drawdown_pct']:6.1f}%  "
              f"PF {full_main['profit_factor']}  windows {[round(w,1) for w in windows]}  variants "
              f"{[round(v,1) for v in variants]}  P(loss) {mc['p_loss']:.0%}  -> {'PROMOTE' if ok else 'reject: ' + '; '.join(why)}",
              flush=True)
    bh = {s: round((d.loc[start:last, 'close'].iloc[-1] / d.loc[start:last, 'close'].iloc[0] - 1) * 100, 1)
          for s, d in data.items()}
    report["buy_and_hold_pct"] = bh
    out = ROOT / "reports"
    out.mkdir(exist_ok=True)
    _deflate(report, trials, out, tag)
    (out / f"{tag}.json").write_text(json.dumps(report, indent=2))
    return report
