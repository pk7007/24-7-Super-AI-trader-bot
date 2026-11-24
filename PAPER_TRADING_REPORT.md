# Paper trading report

**Status: running, no meaningful results yet.** Evaluation window required by the master prompt: 30-90 days minimum. Do not read anything into hours of data.

| Run | Config | Period | Result |
|---|---|---|---|
| 1 (archived: `state/paper_perp_run1_archived_20261124`) | perps, long/short, 2x cap, EMA trend, $1,000 | 2026-11-23 23:45 -> 2026-11-24 ~07:40 UTC | one BTC short opened at $61,171 (stop $66,087), later an ETH short; equity about -0.0%; ETH/SOL were blocked by the venue-price guard for hours (Delta quotes 1-3% off). Retired because it violated the spot/no-short/no-leverage defaults. |
| 2 (`state/paper`) | **spot, long-only, 1x, ensemble**, Rs 10,000 (~$113.6 at 88/USDT) | started 2026-11-24 | see `python -m bot.main report --mode paper` |

**Run 2 note (2026-11-24 07:49 UTC):** BTC, ETH and SOL are all in a downtrend on both ensemble rules, so the long-only spot bot is correctly **in cash with zero trades**. Expect it to stay in cash until an uptrend forms - possibly weeks or months. Each candle now logs a heartbeat line (`candle ... | equity ... | decisions ...`) so "waiting by design" is distinguishable from "broken".

Also run: a 45-day full-engine **replay** on history (7 round trips, stops/flips/time exits/ledger working) - a software test, not evidence of edge.

Assumptions in paper mode: fills at last price +/- 0.05% slippage, stop checks on 1-minute highs/lows, fees 0.10% x GST, spot lot steps assumed, **Binance prices stand in for the execution venue** (no spot exchange connector exists), no spread/depth model. Shadow trading is not implemented.

Review schedule: weekly summary from `report`; first meaningful read after 30 days and at least 10 closed trades; compare against `BACKTEST_REPORT.md` expectations (about 110 trades over 3.6 years is roughly **3 per month** - expect long idle stretches).
