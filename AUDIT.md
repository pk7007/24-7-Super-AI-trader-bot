# Full Audit - India Crypto AI Trading Bot

Audit date: 2026-11-24. Scope: everything in this repository plus the research that led to it.
Scores are out of 10 and are deliberately harsh: a trading system is only as good as its worst part.

## Verdict

| Area | Score | One-line reason |
|------|:----:|-----------------|
| Safety-rule engineering (SAFETY_RULES.md rules 1-6) | **8** | All six rules implemented and covered by tests; proven only against a simulated exchange |
| Test quality | **8** | 34 tests incl. look-ahead, crash recovery, kill-switch restart, stop-failure flatten |
| Data integrity | **6** | Found and worked around corrupt Delta candles; guard exists but is basis-risk by design |
| Strategy edge | **3** | ML model: no edge. Trend rules: weak, one-regime, unproven |
| Live broker readiness | **3** | `DeltaBroker` has never touched the real API |
| Operations / monitoring | **5** | Docker + healthcheck written but never built; no dead-man alert |
| **Overall readiness for real money** | **NOT READY** | A 9/10 is not honest today; see "What it takes" |

## Strategy lab (added 2026-11-24): 3.6 years, Apr 2023 - Nov 2026, BTC/ETH/SOL, all costs included

Buy-and-hold over the same window: BTC +109%, ETH -10%, SOL +209%. Gate = profit factor >= 1.2, profitable in >= 3 of 4
sub-periods, resampled P(loss) <= 25%, and >= 2 of 3 nearby parameter settings profitable.

| Candidate | Return | Max DD | PF | Sub-periods (4) | P(loss) | Verdict |
|---|---|---|---|---|---|---|
| **ensemble** (trend + momentum agree) | +120% (+106% with the bot's 30-day max hold) | -13.5% | 1.86 | +46 / +3 / +4 / +26 | 0% | **PROMOTE** |
| trend_ema (14d) | +66% | -12.2% | 1.36 | +30 / +3 / -1 / +27 | 5% | PROMOTE |
| donchian (20d) | +69% | -17.7% | 1.54 | +42 / -3 / -4 / +25 | 6% | reject: 2/4 sub-periods |
| tsmom (30d) | +32% | -26.4% | 1.09 | +32 / -8 / +6 / +3 | 31% | reject: weak, P(loss) |
| meanrev_rsi | -97% | -97% | 0.57 | all negative | 100% | reject: fees destroy it |

Caveats that matter more than the headline number:
* **Selection bias.** 15 configurations were tested and the best was picked on the same data. Treat +106% as optimistic. Only forward (paper) results can confirm it.
* **It does not clearly beat buying BTC** (+109%); the case for it is a ~14% drawdown instead of a BTC-style crash, and the ability to profit in the 2026 bear market.
* **Only BTC is executable today** (venue guard blocks ETH/SOL, Delta quotes are 1-3% off). BTC contributed under a third of the backtest profit.
* Profit is lumpy: roughly 30% win rate, most return from a few long trends; the middle two sub-periods were nearly flat.
* `STRATEGY=ensemble` selects it. The running paper bot still uses `trend` until you decide to switch.

## What was verified (evidence, not claims)

* `pytest`: 34 passed. Look-ahead test mutates candle *t* and everything after it and proves rows <= *t* are bit-identical.
* Walk-forward backtest, 444 out-of-sample days, Binance candles, costs included (taker 0.05% + 18% GST, slippage, stop slippage, funding).
* Full-engine replay on 45 days of real candles through the paper exchange: entries, exchange stops, flips, time exit, ledger rows.
* Two independent engines (freqtrade and this bot) both lost money with the 15-minute ML idea; agreement between them is the reason to trust the negative result.
* Paper trading on live prices: see "Paper run" below.

## Findings (ordered by severity)

### Critical
1. **The AI model has no predictive edge.** Rank-IC of P(up) vs forward return = -0.008 over 128k out-of-sample rows; the walk-forward strategy lost 68% (BTC itself fell 44%). The class `SignalModel` is kept only as an opt-in (`STRATEGY=ml`). Do not trade it.
2. **Delta India candle history is corrupt.** Versus Binance: 3-6% of BTC/ETH candles off by >2% (impossible spikes such as a 163,116 BTC high), SOL wrong for ~80% of the last 60 days. Root cause not established (exchange data vs ccxt product mapping). Consequence: signals use Binance; Delta is execution only.
3. **`DeltaBroker` is untested.** Written from ccxt source and Delta docs, never run. Unverified: balance asset (`USD` assumed), `fetch_positions` shape, stop-order params (`stop_order_type`, `stop_price`), `fetch_my_trades` mapping, fee parsing. Run on the testnet and verify each call before anything else.
4. **Settlement/tax premise in the brief is wrong.** Delta India perps are quoted/settled in USD (`BTC/USD:USD`), not INR. Whether futures avoid the 1% TDS that applies to spot is unverified; get a CA's opinion. Tax numbers in reports are estimates (30% on gains, no loss set-off).

### High
5. **Basis/venue risk.** Signals are Binance prices, fills are on Delta. Mitigation: `max_venue_deviation` (0.5%) blocks entries if Delta's last price disagrees with the signal feed or cannot be fetched. Exchange-side stops trigger on Delta's own prices, which can differ.
5b. **Observed live (first paper candle, 2026-11-23 23:45 UTC):** the venue guard blocked ETH (Delta price 2.0% off Binance) and SOL (3.1% off), while BTC passed and opened a short with an exchange-side stop. Delta India's ETH/SOL quotes disagree with the global market, so until that is explained only BTC is tradable. This also means two of the three backtested symbols (the profitable ones) may not be executable at those prices.
6. **Trend edge is fragile.** +20.6% / -10.5% max DD over 444 days, but +0.9% in the first half and +19.4% in the second; BTC leg lost money, ETH/SOL made it. One bear-market regime. Win rate 23% (typical for trend following) means long losing streaks are normal.
7. **Paper broker is optimistic in places.** No funding payments, no margin/liquidation model, stops evaluated from 1-minute highs/lows, market fills at last price +/- fixed slippage. Real fills in thin hours will be worse.
8. **No dead-man switch.** If the process dies, exchange-side stops still protect open positions, but nothing alerts you. Telegram alerts exist for events, not for silence. Add an external heartbeat monitor before live.

### Medium
9. Re-entry after a stop happens on the next candle if the trend signal persists (no cooldown); the 3% daily kill-switch is the only brake.
10. Fee model assumes taker 0.05% and 18% GST on fees; verify against your actual Delta fee tier.
11. Candle publication lag is handled by a 4 s delay and a stale-candle check (skips the cycle). Not stress-tested.
12. `state.db` and the paper exchange file are not backed up; a disk loss mid-position relies entirely on reconcile (which flattens unknown positions by default).
13. Docker image and compose file were written but **not built or run** in this session.

### Resolved during this audit
* Live fills carried `realized_pnl = 0` -> engine now computes it from the stored entry (test added).
* `max_venue_deviation` was declared but unused -> implemented and tested (blocks on mismatch and on fetch failure).
* A look-ahead-free trend implementation replaced a first draft whose stop distance was a unit error (15-minute ATR used as daily ATR); caught because the trade count looked absurd.

## What it takes to reach a defensible 9/10

1. Testnet: place, stop, cancel, flatten, restart-reconcile against Delta's real API; fix whatever breaks.
2. Two to four weeks of paper trading across a *different* regime than the backtest, compared against the replay expectation.
3. Walk-forward on a longer history (>= 3 years, include a bull market) with the trend rules frozen; accept or discard on that evidence only.
4. External heartbeat + Telegram; Docker build and a 48 h soak on the VPS.
5. CA sign-off on TDS/tax treatment of the contracts you will actually trade.
6. Start with an amount you can lose completely.
