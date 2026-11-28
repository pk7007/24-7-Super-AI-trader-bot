# Backtest report

> **Latest full audit, simulation version3:** the holding horizon is now aligned at30days and drawdown includes initial capital. The repeated ensemble run backtested +22.03% at0.10% fees and +11.41% at0.50%; **the stress robustness gate failed**. See FULL_AUDIT_2026-11-28.md. Version2 and earlier results below are retained as history, not current evidence.

> **2026-11-28 correction:** earlier spot results below used perpetual lot steps and lacked the minimum-INR order gate. Both defects are fixed; those tables are historical. Fresh development-data reruns at $113.60 are documented in AUDIT_REPORT.md (+23.92% base / +12.20% fee stress for ensemble). They are not fresh holdouts, proof of an edge or full parity with runtime portfolio vetoes.

Data: Binance spot 15-minute candles, validated, BTC/ETH/SOL, 2023-01-24 -> 2026-11-24 (134k candles each). Test window 2023-04-29 -> 2026-11-24 (3.6 years, includes the 2023-24 bull, 2025 chop and the 2026 bear). Buy-and-hold over the window: **BTC +109%, ETH -10%, SOL +209%**.
Engine: `bot/backtest.py` (candle-level, entries at the open of the candle after the signal, stop beats take-profit in the same candle, fees with GST, slippage, stop slippage, 1%-risk sizing, 3% daily kill-switch). Reproduce: `python -m bot.main lab --only trend_ema,donchian,tsmom,ensemble --tag lab_spot`.

## Spot, long-only, 1x leverage (the default profile)

| Strategy | Fees (taker) | Return | Max DD | Profit factor | Trades | Sub-periods (4) | Resampled P(loss) | Gate |
|---|---|---:|---:|---:|---:|---|---:|---|
| ensemble | 0.10% (x1.18 GST) | +101.5% | -14.4% | 2.72 | 111 | +54 / +6 / +5 / +10 | 0% | pass |
| ensemble | **0.25%** (stress) | +95.2% | -15.3% | 2.54 | 114 | +49 / +5 / +4 / +8 | 0% | pass |
| donchian 20d | 0.10% | +81.4% | -15.9% | 2.44 | 84 | +49 / +2 / +2 / +9 | 1% | pass |
| donchian 20d | 0.25% | +72.6% | -15.8% | 2.24 | 84 | +46 / +1 / +1 / +8 | 1% | pass |
| trend EMA 14d | 0.10% | +60.1% | -13.3% | 1.70 | 237 | +37 / +5 / 0 / +9 | 1% | pass |
| trend EMA 14d | 0.25% | +45.5% | -15.2% | 1.52 | 237 | +34 / +4 / -2 / +6 | 6% | pass |
| ensemble | **0.50%** (CoinDCX INR-pair level, unverified) | +78.2% | -17.0% | 2.14 | 114 | +45 / +4 / +2 / +6 | 1% | pass |
| donchian 20d | 0.50% | +61.3% | -18.1% | 1.97 | 81 | +45 / 0 / -1 / +6 | 3% | pass |
| trend EMA 14d | 0.50% | +14.0% | -20.9% | 1.15 | 233 | +23 / 0 / -4 / +2 | 31% | **fail** |
| momentum 30d | 0.10% | +17.9% | -30.1% | 1.15 | 1202 | +36 / -4 / +4 / -8 | 30% | **fail** |
| momentum 30d | 0.25% | -27.4% | -46.0% | 0.78 | 1133 | mostly negative | 87% | **fail** (fees) |

Earlier perpetual long/short runs (kept for the record, not the default): ensemble +106% (-13.9% DD); RSI mean-reversion lost 97%; the 15-minute LightGBM model lost 68%.

## Reading these numbers
* First sub-period dominates (the 2023-24 bull); the middle two are close to flat. This is a **trend follower with ~30% win rate**.
* Position sizes are small (about 17% of equity per position, max 3), so return comes from catching a few large trends, mostly SOL and ETH legs.
* **Selection bias:** 4 families x 3 parameter values were compared on this same window; the best is optimistic. (A pre-registered 2021-2022 holdout was later run once; see below.)
* Spot backtests reuse Delta contract-size rounding (conservative); real spot lot steps differ.
* Not modelled: order-book depth, partial fills, outages, exchange-specific spreads, funding on perps (set to 0 for spot).
* Not done: purged cross-validation (no ML model is promoted), deflated Sharpe, probability of backtest overfitting, multiple-hypothesis correction. A strategy "passes" only by the lab's own gate (profit factor >= 1.2, >= 3 of 4 profitable sub-periods, resampled P(loss) <= 25%, >= 2 of 3 nearby parameters profitable).


## Fee stress under policy limits (2026-11-24)
Spot, long-only, 1x, ensemble, 0.5% risk per trade, 2 positions, daily/weekly/monthly limits 1/3/5%, Binance candles 2023-04 to 2026-11, 3.6 years. Taker = maker = fee, plus 18% GST on fees. Slippage (0.05%, stop 0.10%) was **not** scaled, so the real cost increase is smaller than the label says.

| Fee per side | Multiple of base | Return | Max DD | Profit factor | P(loss), resampled | Gate |
|---|---|---:|---:|---:|---:|---|
| 0.10% | 1x | +22.5% | -4.9% | 2.44 | 1% | pass |
| 0.15% | 1.5x | +21.8% | -5.0% | 2.36 | 1% | pass |
| 0.20% | 2x | +21.0% | -5.2% | 2.27 | 1% | pass |
| 0.30% | 3x | +19.5% | -5.6% | 2.11 | 2% | pass |
| 0.50% | 5x (CoinDCX-like INR fee, unverified) | +16.8% | -6.0% | 1.86 | 5% | pass |

Fees are not what breaks this strategy: it trades rarely, so even 5x fees cost about 6 points of return over 3.6 years. The limiting factor is the modest base return (about 6% a year before tax). Cost scenarios not yet run: scaled slippage, spread widening, latency, partial fills, exchange outage, and price-shock tests. Files: `reports/lab_policy_fee_*.json`.


## Pre-registered holdout, 2021-2022 (2026-11-24)
Protocol and pass criteria were written first in [HOLDOUT_PROTOCOL.md](HOLDOUT_PROTOCOL.md); the run was done once with the frozen policy configuration. Data: Binance 15m BTC/ETH/SOL fetched for 2021-01-01 to 2023-01-24 (the fetch returned candles to 2023-02-01, an 8-day overlap with the tuning window); evaluated after a 95-day warm-up, so roughly 2021-04 to 2023-02. This covers the end of the 2021 bull market and the whole 2022 crash, which the strategy was never tuned on.

| | Ensemble (policy limits) | Buy and hold, same window |
|---|---:|---:|
| Return | **+5.3%** | BTC -61.0%, ETH -25.2%, SOL +4.6% |
| Max drawdown | -5.5% | (BTC fell far more) |
| Profit factor | 1.87 | |
| Trades | 40 (32.5% winners) | |
| Sub-period returns | +3.6%, -0.9%, +0.9%, +2.3% | |
| Nearby parameters (10/14/21 days) | +5.4%, +5.3%, +4.8% | |
| Resampled chance of a loss | 10% | |

**Verdict: passed the pre-declared minimum criteria (lab gate, DD <= 8%, >= 30 trades), but this is weak evidence:** 40 trades, resampled chance of a loss 10% (5th-percentile outcome about -1.2%), exactly 3 of 4 sub-periods profitable (the minimum), and about 2.8% a year before 30% tax and 1% TDS, which is below Indian risk-free rates. Sitting in cash through a bear market is what a long-only trend filter is designed to do, so the crash result was largely expected. Independently checked by `quant-validator` (numbers reproduced from the JSON). The JSON did not record risk per trade, positions or loss limits at the time; `run_lab` now writes an `effective_config` block. What it shows: the strategy protected capital through a crash where BTC lost about 61%, and stayed slightly positive. What it does not show: strong returns. About +5% over roughly 1.8 years is about 3% a year before tax, and 40 trades is a small sample. File: `reports/holdout_2021_2022.json`.

## Re-run after cost-inclusive sizing (2026-11-25)
The bot sized each trade from the stop distance alone, so a full stop-out lost about 0.53% of equity once round-trip fees, GST and slippage were counted, above the 0.5% policy. Found by the new `crypto-risk` check. `position_units` now divides the risk budget by (stop distance + round-trip cost), so a stop-out loses at most 0.5% including costs. Trades are slightly smaller. Same data, same settings otherwise; the tables above are the pre-fix numbers (files kept in `reports/pre_cost_sizing/`).

| Run | Before: return / DD / PF / trades | After: return / DD / PF / trades | Gate after |
|---|---|---|---|
| 0.10% fee (base) | +22.5% / -4.9% / 2.44 / 85 | **+21.8% / -4.7% / 2.50 / 83** | pass |
| 0.15% fee | +21.8% / -5.0% / 2.36 / 85 | +21.1% / -4.8% / 2.42 / 83 | pass |
| 0.20% fee | +21.0% / -5.2% / 2.27 / 85 | +22.0% / -4.6% / 2.50 / 81 | pass |
| 0.30% fee | +19.5% / -5.6% / 2.11 / 85 | +19.5% / -4.5% / 2.37 / 80 | pass |
| 0.50% fee | +16.8% / -6.0% / 1.86 / 85 | +15.9% / -4.7% / 2.10 / 75 | pass |
| Holdout 2021-22 (**second look**, labelled re-run) | +5.3% / -5.5% / 1.87 / 40 | +5.1% / -5.5% / 1.84 / 40 | pass (same criteria) |

Smaller trades fall below the Rs 100 minimum order more often at high fees, so fewer trades happen; that path change is why the 0.20% row came out slightly above the base. Treat differences under about 1 point of return as noise. The holdout was meant to be used once; this re-run is a second look after a mechanical correction (no parameter was tuned), so it is not new out-of-sample evidence. The original one-shot result stays in `reports/holdout_2021_2022.json`; the re-run is `reports/holdout_2021_2022_rerun_costsizing.json`.
