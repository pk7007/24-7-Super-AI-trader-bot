# Audit report - 2026-11-26 (supersedes the 2026-11-24 version; the older interim `AUDIT.md` is kept for history)

**Decision: NOT READY for live capital. Paper trading only.**
Weighted score **5.2 / 10** (was 4.4 on 2026-11-24). Readiness scorer (`python -m bot.readiness`, rerun today): **43/100, DEVELOPMENT ONLY**.
A high score could never override the blockers below.

## What was run for this audit (2026-11-26)

| Check | Result |
|---|---|
| `python -m pytest -q` | **191 passed** (12.5 s), 1 deprecation warning |
| Frontend `npm test` / `npm run typecheck` | 23 passed / 0 errors (run 2026-11-26 before the merge) |
| `python -m bot.readiness` | 43/100, DEVELOPMENT ONLY, state PAPER |
| `replay --days 60`, spot, current policy, $113.60 | **0 trades** (window 2026-09-25 -> 2026-11-24; all three coins in downtrends) |
| Paper bot `state/paper` | running since 2026-11-24 08:00 UTC; **0 fills**, equity $113.60 |
| Shadow bot `state/shadow` | running since 2026-11-24 12:45 UTC; **0 order intents sent**, equity $113.60 |
| Candle coverage (log lines vs expected 15m candles) | paper **164/230 = 71%**, shadow **145/211 = 69%** |
| Errors in bot logs | 12 "step failed", 2 data-fetch failures after retries on all hosts, 1 monitor failure |
| Lab, current policy (not rerun today; `reports/lab_spot_policy_mp2.json`) | 2023-04-29 -> 2026-11-24: +21.8%, PF 2.5, 83 trades, max DD -4.7%, resampled P(loss) 1.3%, gate passed |
| Holdout, never used for selection (`reports/holdout_2021_2022_rerun_costsizing.json`) | 2021-04 -> 2023-02: PF 1.84, 40 trades, max DD -5.5% |

The lab was not rerun today (results are from 2026-11-24 with the same policy). No independent second-reviewer pass was done on these scores.

## Paper-trading benchmark: not yet testable

| Metric | Target | Now |
|---|---|---|
| Completed paper trades | >= 100 and >= 30 days | **0 trades, about 2.4 days** |
| Profit factor, Sharpe, win rate, slippage | see MASTER_LOOP_PROMPT | not measurable with 0 trades |
| Uptime | >= 99.9% | **about 70%** of candles processed (PC sleep, restarts, Binance network errors) |

At about 2.6 trades a month, 100 trades would take about 3 years. Overall is capped at 6 while no benchmark is met; the cap does not bind at 5.2.

## Blockers (any one blocks live trading)
1. **No spot execution path.** No spot connector exists; CoinDCX spot has no documented exchange-side stop order, sandbox or trade-only key scope ([EXCHANGE_RESEARCH.md](EXCHANGE_RESEARCH.md)).
2. **`DeltaBroker` has never run against a real API** (testnet check needs a key from `demo.delta.exchange`).
3. **No forward evidence:** 0 paper trades, 0 shadow intents.
4. **Legal and tax assumptions unverified** (COMPLIANCE.md); exchange eligibility for an Indian resident not established.
5. **Exposed production credentials** (SECURITY.md) are still listed as "rotate these"; this audit cannot confirm they were deleted on the exchange.

## Weighted scores (0-10; evidence or the score stays low)

| Domain | Weight | 11-24 | **11-26** | Evidence and what is missing |
|---|---:|---:|---:|---|
| Quantitative strategy quality | 10% | 6 | **6** | Gate passed, PF 2.5 in sample, PF 1.84 on an untouched holdout. But +21.8% over 3.6 years trails buy-and-hold (BTC +109%, SOL +209%; ETH -10%) and there are no forward trades |
| AI / machine learning | 8% | 3 | **3** | LightGBM honestly rejected and shown as rejected; no champion-challenger cycle logged, no drift or calibration work |
| Market data quality | 8% | 5 | **5** | Candle validation, multi-host retry (tested). Live feed missed about 30% of candles; single signal source (Binance) differs from the execution venue (Delta) |
| Backtesting & statistical validation | 12% | 6 | **7** | Walk-forward, Monte Carlo, sub-periods, parameter neighbours, fee stress 0.10-0.50%, and now a true holdout. Missing: deflated Sharpe, >= 300 out-of-sample trades |
| Risk management | 15% | 5 | **7** | Added: daily 1% / weekly 3% / monthly 5% limits, cost-inclusive 0.5% sizing, risk-check CLI, all tested. Missing: VaR/ES, correlation and exposure caps; no protection verified on a real exchange |
| Execution reliability | 10% | 3 | **3** | Paper and shadow brokers run; reconcile tested on a simulator. No spot adapter, live broker untested, 12 step failures in 2.4 days |
| Portfolio management | 5% | 3 | **3** | 2 positions, per-trade risk; no allocation, rebalancing or correlation |
| Security | 7% | 4 | **4** | Secret hygiene and consent gates tested; dashboard localhost-only, GET-only, CSP, secrets test. Exposed keys not confirmed rotated; `pip-audit` not run |
| Regulatory & tax | 5% | 2 | **2** | Ledger and estimates only; nothing verified by a professional |
| Infrastructure & reliability | 5% | 3 | **4** | Added: Windows scheduled tasks with auto-restart, feed-resilience tests. Still a single sleeping PC (71% coverage), Docker image not soak-tested, no tested backups |
| Testing & verification | 5% | 6 | **7** | 191 Python + 23 frontend tests on financial invariants and API safety. No property-based, chaos or end-to-end browser tests |
| Monitoring & analytics | 3% | 3 | **5** | Added: alerts (no-data, step failure, stale feed; fired records in `state/alerts_fired.json`) and the dashboard Health page. No external heartbeat if the PC itself is off |
| User interface | 2% | 0 | **7** | Read-only dashboard, 15 pages from real data (FRONTEND_SCORECARD.md 7.8/10, self-scored); no E2E or screen-reader pass |
| Cost efficiency | 3% | 7 | **7** | Zero paid services; benefit unproven |
| Documentation | 2% | 6 | **7** | Accurate, candid reports incl. six frontend reports; some overlap between older reports |
| **Weighted total** | 100% | **4.4** | **5.2** | |

## Biggest findings
1. **The bot has not traded yet.** 0 paper fills, 0 shadow intents, and a 60-day replay also gives 0 trades: the ensemble is correctly holding cash in downtrends, but there is no forward evidence at all.
2. **Uptime is about 70%, not 99.9%.** Missed candles come from the PC sleeping, restarts and Binance network errors. This is the cheapest real improvement.
3. **The strategy trails buy-and-hold on return.** It wins on drawdown (-4.7% vs large coin drawdowns), not on profit.
4. **Exposed production keys** still need deleting on Delta; only you can do this.

## What a fair path to 9/10 needs
Spot connector plus a sandbox or testnet order test; 30-90 days of paper including shadow trading on an always-on machine; VaR and correlation or exposure caps; verified legal and tax setup; backups, an external heartbeat and a Docker soak test; deflated Sharpe on the lab; one logged champion-challenger decision; then a small, manually authorised live pilot.
