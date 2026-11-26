# Audit report - 2026-11-26, re-scored after the code fixes (supersedes the 2026-11-24 version; `AUDIT.md` kept for history)

**Decision: NOT READY for live capital. Paper trading only.**
Weighted score **5.6 / 10** (4.4 on 2026-11-24, 5.2 this morning). Readiness scorer (`python -m bot.readiness`): **50/100, DEVELOPMENT ONLY** (was 43).
A high score could never override the blockers below. 9/10 is not reachable by code alone (see the last section).

## What was run (2026-11-26)

| Check | Result |
|---|---|
| `python -m pytest -q` (run by the readiness scorer) | **230 passed** |
| Frontend `npm test` / `npm run typecheck` | 23 passed / 0 errors (before the morning merge; frontend unchanged since) |
| `python -m bot.readiness` | 50/100, DEVELOPMENT ONLY, state PAPER |
| Lab rerun, current policy, all 5 strategies (`lab_spot_policy_mp2`) | ensemble **reproduced exactly**: +21.8%, PF 2.5, 83 trades, max DD -4.7%, P(loss) 1.3% |
| Lab rerun at 0.50% fees, all 5 strategies (`lab_policy_fee_0.005`) | ensemble reproduced exactly: +15.9%, PF 2.1 |
| **Deflated Sharpe** (new, `bot/stats.py`) | ensemble Sharpe 1.16/yr; **DSR 0.000** counting all 97 trials, **0.780** within the trend family; bar is 0.95 |
| **Champion-challenger** (new, `python -m bot.experiments`) | 4 challengers, **all rejected** with reasons; logged in `reports/experiments.md` (109 trials counted) |
| **Portfolio ES cap** on live daily data (new, `bot/portfolio_risk.py`) | single coin 0.26-0.39% of equity, any pair 0.63-0.77%, cap 2%; coin correlations 0.85-0.90 |
| **Backup drill** (new, `python -m bot.backup --drill`) | **passed**: 4 files, hashes + SQLite integrity OK, restored, row counts match |
| `pip-audit` on `requirements.txt` and the installed venv | **no known vulnerabilities** (freqtrade could not be checked: not on PyPI) |
| `replay --days 60`, spot, $113.60 | 0 trades (all coins in downtrends) |
| Paper / shadow bots | running; **0 fills, 0 order intents**; candle coverage before the uptime fix 71% / 69% |

Not done: Docker image build and soak (Docker Desktop not running; belongs on the always-on VPS), new uptime measurement (needs a day or two of running), independent second-reviewer pass.

## Paper-trading benchmark: not yet testable

| Metric | Target | Now |
|---|---|---|
| Completed paper trades | >= 100 and >= 30 days | **0 trades, about 2.5 days** |
| Profit factor, Sharpe, win rate, slippage | see MASTER_LOOP_PROMPT | not measurable with 0 trades |
| Uptime | >= 99.9% | about 70% before the fix; not yet re-measured |

Overall is capped at 6 while no benchmark is met. At about 2.6 trades a month, 100 trades would take about 3 years.

## Blockers (any one blocks live trading)
1. **No spot execution path.** No spot connector; CoinDCX spot has no documented exchange-side stop order, sandbox or trade-only key scope ([EXCHANGE_RESEARCH.md](EXCHANGE_RESEARCH.md)).
2. **`DeltaBroker` has never run against a real API** (testnet check needs a key from `demo.delta.exchange`).
3. **No forward evidence:** 0 paper trades, 0 shadow intents.
4. **Legal and tax assumptions unverified** (COMPLIANCE.md).
5. **Exposed production credentials** (SECURITY.md) not confirmed deleted on the exchange.

## Weighted scores (0-10; evidence or the score stays low)

| Domain | Weight | 11-24 | 11-26 am | **11-26 pm** | Evidence and what is missing |
|---|---:|---:|---:|---:|---|
| Quantitative strategy quality | 10% | 6 | 6 | **5** | Gate passed, holdout PF 1.87. **New negative evidence:** deflated Sharpe 0.000 (all trials) / 0.780 (trend family), so the edge is not yet distinguishable from selection luck; trails buy-and-hold on return; no forward trades |
| AI / machine learning | 8% | 3 | 3 | **4** | Champion-challenger pipeline built and tested; first logged decision (4 challengers rejected, reasons and trial count recorded). No AI model beats the no-model baseline |
| Market data quality | 8% | 5 | 5 | **5** | Validation and multi-host retry; failed candles now retried. Coverage not yet re-measured; signal source differs from execution venue |
| Backtesting & statistical validation | 12% | 6 | 7 | **8** | Walk-forward, Monte Carlo, sub-periods, neighbours, fee stress, true holdout, and now a deflated Sharpe with a conservative trial count; reruns reproduce exactly. Missing: >= 300 out-of-sample trades |
| Risk management | 15% | 5 | 7 | **8** | Added: correlation-aware 1-day 97.5% expected-shortfall cap (2% of equity, policy ceiling, fail-closed) and gross-exposure cap in the engine, 12 tests. At current sizing the ES cap is a backstop (worst pair 0.77%). Not verified on a real exchange |
| Execution reliability | 10% | 3 | 3 | **3** | Unchanged: no spot adapter, live broker untested |
| Portfolio management | 5% | 3 | 3 | **4** | Entries now see the joint, correlated risk of what is already held; no allocation or rebalancing |
| Security | 7% | 4 | 4 | **5** | Added: `pip-audit` clean on requirements and venv; heartbeat URL handled as a secret (tested). Exposed keys still not confirmed rotated |
| Regulatory & tax | 5% | 2 | 2 | **2** | Unchanged |
| Infrastructure & reliability | 5% | 3 | 4 | **5** | Added: keep-awake, same-candle retry, consistent backups with a passed restore drill. Backups not yet scheduled; Docker unbuilt; single PC |
| Testing & verification | 5% | 6 | 7 | **7** | 230 Python + 23 frontend tests. No property-based, chaos or end-to-end browser tests |
| Monitoring & analytics | 3% | 3 | 5 | **5** | External heartbeat built and tested but **not configured** (needs your HEARTBEAT_URL); rises to 6 once pings are delivered |
| User interface | 2% | 0 | 7 | **7** | Read-only dashboard (self-scored 7.8/10) |
| Cost efficiency | 3% | 7 | 7 | **7** | Zero paid services |
| Documentation | 2% | 6 | 7 | **7** | Reports kept current with the code |
| **Weighted total** | 100% | **4.4** | **5.2** | **5.6** | |

## Biggest findings
1. **Selection bias is real.** After counting the 97 strategy settings tried, the ensemble's backtest Sharpe (1.16/yr) is below what the luckiest skill-less strategy would show. Even within the trend family the deflated Sharpe is 0.78, short of 0.95. Only forward paper trades can settle this.
2. **The bot has not traded yet** (0 paper fills, 0 shadow intents, 0 trades in a 60-day replay).
3. **The three coins move together** (daily correlation 0.85-0.90): holding two positions gives little diversification. The new ES cap counts this.
4. **No challenger beats the champion.** Donchian comes closest (better PF, lower return) but has no holdout of its own.

## Why 9/10 is out of reach now, and what moves it
The overall score is capped at 6 until the paper benchmark is met, and the remaining low areas need things only the user or time can provide:

| Needs | Moves |
|---|---|
| Delete the leaked Delta keys; create a demo (testnet) key; run `testnet-check` | Security, Execution |
| Choose a spot venue with an exchange-side stop order, then build its adapter | Execution (largest gap) |
| Chartered-accountant confirmation of tax and TDS | Regulatory |
| 30-90 days of paper and shadow trading on an always-on machine (VPS) | Strategy quality, benchmark cap, uptime |
| Set `HEARTBEAT_URL` (free healthchecks.io check) | Monitoring |
| Approve a daily scheduled backup task | Infrastructure |
