"""Walk-forward backtest with realistic costs (fees+GST, slippage, funding, exchange-stop gaps).

Conventions (identical to the live engine):
  * row t of every feature/probability is known at the OPEN of candle t (features are shifted);
  * entries fill at open[t] (+slippage); the entry candle itself can already hit the stop;
  * stop and take-profit in the same candle -> the STOP wins (pessimistic);
  * trades are force-closed after ``horizon`` candles, on a confident model flip, or by the
    daily kill-switch.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from .config import Settings
from .feeds import DEFAULT_CONTRACT_SIZE, SPOT_STEP
from .features import build_features, make_labels
from .model import PROB_COLUMNS, SignalModel
from .risk import DailyKillSwitch, position_units, stop_price, to_contracts, tp_price
from .strategy import decide, should_exit_on_flip

# Increment when execution assumptions change; old reports cannot prove current readiness.
SIMULATION_VERSION = 3


def prepare(cfg: Settings, data: dict[str, pd.DataFrame]):
    feats = {s: build_features(d) for s, d in data.items()}
    labels = {s: make_labels(d, feats[s], cfg.horizon, cfg.label_k) for s, d in data.items()}
    return feats, labels


def walk_forward_probs(cfg: Settings, data, feats, labels, start: pd.Timestamp, end: pd.Timestamp,
                       model_factory=SignalModel) -> dict[str, pd.DataFrame]:
    """Out-of-sample probabilities: each test window is scored by a model trained only on the
    ``train_days`` before it, excluding rows whose labels were not yet resolved."""
    probs = {s: pd.DataFrame(np.nan, index=d.index, columns=PROB_COLUMNS) for s, d in data.items()}
    tf = pd.Timedelta(minutes=cfg.tf_minutes)
    t0 = start
    while t0 < end:
        t1 = min(t0 + pd.Timedelta(days=cfg.test_days), end)
        cut = t0 - cfg.horizon * tf  # labels of rows >= cut peek into the test window
        lo = t0 - pd.Timedelta(days=cfg.train_days)
        Xs, ys = [], []
        for s in data:
            m = (feats[s].index >= lo) & (feats[s].index < cut)
            Xs.append(feats[s][m]), ys.append(labels[s][m])
        X, y = pd.concat(Xs), pd.concat(ys)
        if y.notna().sum() < 2000:
            t0 = t1
            continue
        model = model_factory().fit(X, y)
        for s in data:
            m = (feats[s].index >= t0) & (feats[s].index < t1)
            probs[s].loc[m, PROB_COLUMNS] = model.predict_proba(feats[s][m]).values
        t0 = t1
    return probs


@dataclass
class Trade:
    symbol: str
    side: int
    entry_ts: pd.Timestamp
    exit_ts: pd.Timestamp
    entry: float
    exit: float
    contracts: int
    pnl: float  # net of all costs
    fees: float
    reason: str
    exit_notional: float = 0.0  # quote-currency value sold/closed (basis for 1% TDS estimates)


@dataclass
class Result:
    trades: list[Trade] = field(default_factory=list)
    curve: pd.Series = field(default_factory=lambda: pd.Series(dtype=float))
    metrics: dict = field(default_factory=dict)


def simulate(cfg: Settings, data: dict[str, pd.DataFrame], feats, probs, start, end,
             contract_sizes: dict[str, float] | None = None) -> Result:
    cs_map = contract_sizes if contract_sizes is not None else (SPOT_STEP if cfg.market == "spot" else DEFAULT_CONTRACT_SIZE)
    syms = list(data)
    idx = sorted(set().union(*[set(d.index[(d.index >= start) & (d.index < end)]) for d in data.values()]))
    idx = pd.DatetimeIndex(idx)
    A = {s: {k: data[s][k].reindex(idx).to_numpy() for k in ("open", "high", "low", "close")} for s in syms}
    ATR = {s: feats[s]["atr_pct"].reindex(idx).to_numpy() for s in syms}
    PD = {s: probs[s]["p_down"].reindex(idx).to_numpy() for s in syms}
    PU = {s: probs[s]["p_up"].reindex(idx).to_numpy() for s in syms}

    fee_t, fee_m = cfg.taker_fee * cfg.gst, cfg.maker_fee * cfg.gst
    fund = cfg.funding_per_8h * cfg.tf_minutes / 480
    cash = cfg.start_equity
    pos: dict[str, dict] = {}
    trades: list[Trade] = []
    curve = np.full(len(idx), np.nan)
    ks = DailyKillSwitch(cfg.daily_loss_limit)
    ks_w = DailyKillSwitch(cfg.weekly_loss_limit)
    ks_m = DailyKillSwitch(cfg.monthly_loss_limit)

    def mark(i: int, field_: str) -> float:
        eq = cash
        for s, p in pos.items():
            px = A[s][field_][i]
            if px == px:
                eq += p["side"] * (px - p["entry"]) * p["units"]
        return eq

    def close(s: str, i: int, px: float, reason: str, fee_rate: float) -> None:
        nonlocal cash
        p = pos.pop(s)
        gross = p["side"] * (px - p["entry"]) * p["units"]
        fee = p["units"] * px * fee_rate
        cash += gross - fee
        net = gross - fee - p["fees_in"] - p["funding"]
        trades.append(Trade(s, p["side"], p["ts"], idx[i], p["entry"], px, p["n"], net,
                            fee + p["fees_in"], reason, exit_notional=p["units"] * px))

    for i, ts in enumerate(idx):
        _o = mark(i, "open")
        _iso = ts.isocalendar()
        ks.roll(ts.strftime("%Y-%m-%d"), _o)
        ks_w.roll(f"{_iso[0]}-W{_iso[1]:02d}", _o)
        ks_m.roll(ts.strftime("%Y-%m"), _o)
        # ---- entries at the open ------------------------------------------------
        if not (ks.halted or ks_w.halted or ks_m.halted):
            for s in syms:
                if s in pos or len(pos) >= cfg.max_positions:
                    continue
                if A[s]["open"][i] != A[s]["open"][i]:
                    continue
                side = decide(PD[s][i], PU[s][i], cfg)
                if not side:
                    continue
                cs = cs_map[s]
                px_open = A[s]["open"][i]
                n = to_contracts(position_units(mark(i, "open"), px_open, ATR[s][i], cfg), cs)
                if n <= 0:
                    continue
                if n * cs * px_open * cfg.usdt_inr < cfg.min_order_inr:
                    continue
                entry = px_open * (1 + side * cfg.slippage)
                units = n * cs
                fee_in = units * entry * fee_t
                cash -= fee_in
                pos[s] = {"side": side, "entry": entry, "units": units, "n": n, "ts": ts, "bars": 0,
                          "stop": stop_price(side, entry, ATR[s][i], cfg),
                          "tp": tp_price(side, entry, ATR[s][i], cfg), "fees_in": fee_in, "funding": 0.0}
        # ---- manage open positions through this candle --------------------------
        for s in list(pos):
            p = pos[s]
            hi, lo, cl = A[s]["high"][i], A[s]["low"][i], A[s]["close"][i]
            if hi != hi:
                continue
            p["bars"] += 1
            f_cost = p["units"] * cl * fund
            p["funding"] += f_cost
            cash -= f_cost
            hit_stop = lo <= p["stop"] if p["side"] > 0 else hi >= p["stop"]
            hit_tp = hi >= p["tp"] if p["side"] > 0 else lo <= p["tp"]
            if hit_stop:  # pessimistic: stop first even if TP also touched
                close(s, i, p["stop"] * (1 - p["side"] * cfg.stop_slippage), "stop", fee_t)
            elif hit_tp:
                close(s, i, p["tp"], "tp", fee_m)
            elif p["bars"] >= cfg.horizon:
                close(s, i, cl * (1 - p["side"] * cfg.slippage), "time", fee_t)
            elif i + 1 < len(idx) and should_exit_on_flip(p["side"], PD[s][i + 1], PU[s][i + 1], cfg):
                close(s, i, cl * (1 - p["side"] * cfg.slippage), "flip", fee_t)
        # ---- end-of-candle equity & kill-switch ---------------------------------
        eq = mark(i, "close")
        if any([ks.check(eq), ks_w.check(eq), ks_m.check(eq)]):
            for s in list(pos):
                close(s, i, A[s]["close"][i] * (1 - pos[s]["side"] * cfg.slippage), "kill_switch", fee_t)
            eq = cash
        curve[i] = eq

    res = Result(trades=trades, curve=pd.Series(curve, index=idx).ffill())
    res.metrics = metrics(cfg, res)
    return res


def metrics(cfg: Settings, res: Result) -> dict:
    c, t = res.curve.dropna(), res.trades
    if c.empty:
        return {}
    daily = c.resample("1D").last().dropna()
    r = daily.pct_change().dropna()
    peak = c.cummax().clip(lower=cfg.start_equity)
    dd = (c / peak - 1).min()
    pnls = np.array([x.pnl for x in t]) if t else np.array([0.0])
    wins, losses = pnls[pnls > 0].sum(), -pnls[pnls < 0].sum()
    by_sym = {}
    for x in t:
        by_sym.setdefault(x.symbol, []).append(x.pnl)
    gains_tax = float(sum(max(x.pnl, 0.0) for x in t)) * cfg.usdt_inr * 0.30
    return {
        "start_equity": cfg.start_equity,
        "end_equity": round(float(c.iloc[-1]), 2),
        "return_pct": round((c.iloc[-1] / cfg.start_equity - 1) * 100, 2),
        "max_drawdown_pct": round(float(dd) * 100, 2),
        "sharpe_daily_annualised": round(float(r.mean() / r.std() * np.sqrt(365)), 2) if r.std() > 0 else 0.0,
        "trades": len(t),
        "win_rate_pct": round(float((pnls > 0).mean() * 100), 1) if t else 0.0,
        "profit_factor": round(float(wins / losses), 2) if losses > 0 else float("inf"),
        "avg_trade_usd": round(float(pnls.mean()), 3),
        "fees_paid_usd": round(float(sum(x.fees for x in t)), 2),
        "days": round((c.index[-1] - c.index[0]).days, 1),
        "exits": {k: sum(1 for x in t if x.reason == k) for k in {x.reason for x in t}},
        "per_symbol_pnl_usd": {k: round(float(sum(v)), 2) for k, v in by_sym.items()},
        "est_india_tax_30pct_inr": round(gains_tax, 0),
        "est_tds_1pct_of_sales_inr": round(sum(x.exit_notional for x in t) * cfg.usdt_inr * 0.01, 0),
        "total_traded_notional_usd": round(float(sum(x.exit_notional for x in t)), 0),
    }
