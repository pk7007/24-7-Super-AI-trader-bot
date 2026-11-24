# Holdout protocol (written BEFORE the run, 2026-11-24)

**Why the old window is not a holdout.** The ensemble and its 14-day setting were chosen while looking at 2023-04 -> 2026-11, and several candidates were compared on it. Any result there is optimistic.

**The holdout.** Binance 15-minute candles for BTC, ETH and SOL from 2021-01-01 to 2023-01-23 (everything before the first candle the project ever used). It includes the 2021 bull market and the 2022 crash. The strategy was never tuned on it.

**Frozen configuration (no changes after seeing results):** spot, long-only, 1x, ensemble with the 14-day main parameter, stop 2 ATR, 0.5% risk per trade, 2 positions, daily/weekly/monthly loss limits 1/3/5%, taker=maker 0.10% + 18% GST, slippage 0.05%, stop slippage 0.10%.

**Run once.** `run_lab(only=ensemble)` on the holdout, one time. If it fails, the failure is reported as is; no parameter is changed and re-run against this data.

**Pre-declared pass criteria (all required):**
1. Lab promotion gate passes (PF >= 1.2 and positive return; >= 3 of 4 sub-periods profitable; resampled P(loss) <= 25%; >= 2 of 3 nearby parameters profitable).
2. Max drawdown <= 8%.
3. At least 30 completed trades (otherwise the result is "inconclusive", not a pass).
4. Net return reported next to buy-and-hold for the same window; underperforming buy-and-hold is allowed but must be stated.

**Limits that remain even if it passes:** one holdout is one sample of history; trade count may be small; Binance candles are not the execution venue; this does not replace forward paper/shadow testing.
