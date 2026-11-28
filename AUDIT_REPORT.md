# Audit report — 2026-11-28

**Latest full audit: [FULL_AUDIT_2026-11-28.md](FULL_AUDIT_2026-11-28.md), 5.1/10 engineering / 41 readiness, NO-GO for live money.** It supersedes the earlier scoped audit below: 378 Python tests passed on Windows and Linux, 25 frontend tests passed, advisory scans and container/browser checks completed. The running bots were not restarted.

## Earlier scoped audit — retained for provenance

**Decision: NO-GO for live capital. Current engineering audit: 4.7/10 (weighted 4.66).** This replaces the older 5.8 assessment below. The lower score reflects newly exposed backtest inconsistencies and stricter treatment of missing evidence, despite the fixes. Scores are engineering judgments, not probabilities of success. The master prompt's 9/10 exit conditions are not met.

The separate evidence-based readiness scorer is now **44/100, DEVELOPMENT ONLY** (previously 56). Twelve points from obsolete simulation reports are no longer credited. This scorer uses the completed 278-test XML via `C:/tb/scratch/audit_readiness_20261128.py`; reports and LIVE_TRADING_READINESS.md were refreshed without running another suite. Paper and shadow each have **zero completed trades**; roughly four calendar days since the first log is not four days of continuous uptime.

## Scope and evidence

Reviewed local `main` against GitHub `pk7007/24-7-Super-AI-trader-bot`, commit `e8cb6c6a03633bfde550c69c396193bee0e9c843`. At inspection, GitHub had no open PRs and no Actions runs; no workflow is tracked. Changes from this audit are local and uncommitted. Credentials were not inspected; running bots and scheduled tasks were not restarted or changed.

- Full offline Python suite: **278 passed**, with one Starlette/httpx deprecation warning. Evidence: `reports/audit_tests.xml`. Windows sandbox loopback prevents asyncio's internal socket pair from starting; the suite passed outside that restriction, with dotenv loading and external socket connections disabled by fixtures.
- Frontend: **23 passed**, TypeScript check and production build passed. No browser E2E or accessibility audit was performed.
- Independent reviewers reproduced bugs, reviewed fixes, and checked risk/quantitative implications. The first protective-exit patch had a restart accounting gap; it was fixed and independently re-reviewed.
- Cached-data reruns: all five lab candidates at 0.10% and 0.50% fees, plus an isolated seven-day full-engine replay. Outputs: `reports/audit_20261128/`; reproduction script: `C:/tb/scratch/audit_research_20261128.py`. No new data download or fresh holdout. Older trial history was excluded from that isolated folder, so its DSR cannot represent all historical trials.

## Fixed findings

| Priority | Finding | Fix and evidence |
|---|---|---|
| P1 | Restore could escape its target on Windows; contents were not verified before writing | Exact archive/manifest allowlist, preflight integrity checks, destination containment; unsafe-path and tampering regressions in `test_backup.py` |
| P1 | Missing stops and entry-ledger failures could leave positions unprotected | Stop before ledger; repair-or-flatten on startup/candle/monitor; emergency exits retried, entries blocked, stops/state retained until flat; nine failure/restart drills in `test_stop_recovery.py` |
| P1 | Interrupted entry accounting could silently resume after restart | Persistent accounting halt; overview exposes it. Operator ledger reconciliation remains required |
| P1 | Spot configuration reached Delta's perpetual adapter | Adapter rejects non-perpetual profile before credentials/network construction; guard regression |
| P1 | Spot backtest and replay used perpetual lot sizes; backtest omitted INR minimum orders | Market-specific lot defaults, explicit overrides preserved, minimum gate matches runtime; direct backtest/feed regressions. Old tables are historical |
| P2 | Obsolete lab outputs could continue earning readiness points | Future lab outputs record the simulation version; scorer rejects old/unversioned evidence, with regression. This audit's isolated reruns finished before the metadata addition and receive no readiness credit |
| P2 | Failed/empty backup drill could report success; retention flag ignored | Nonzero failure exit, empty backups rejected, retention forwarded/validated; invalid new backups do not rotate valid recovery points; atomic ZIP publication and collision refusal |
| P2 | Malformed heartbeat status broke monitoring; future timestamps counted as recent | Defensive status parsing and nonnegative evidence age; offline failure tests |
| P2 | Log mtime made error loops look healthy | Compose now checks a recent successful candle, rejecting errors/no-data/future/stale events; five health tests. Docker execution remains unverified |
| P2 | Raw SQLite URIs broke on paths containing `#` | Proper file-URI encoding for backup/API/risk readers; special-character backup drill regression |
| P2 | API tests depended on the user's files and weakly allowed writes | Isolated fixtures and exact before/after state equality; tests do not load dotenv or contact external services |

## Corrected development backtests

Spot, long-only, 1x; $113.60 starting equity, existing cached Binance candles, current configured costs/risk defaults. No strategy was switched or promoted into runtime.

| Ensemble | Return | Max drawdown | Profit factor | Trades | Isolated-trial DSR |
|---|---:|---:|---:|---:|---:|
| 0.10% fee per side, GST/slippage included | +23.92% | -6.94% | 2.02 | 108 | 0.000 |
| 0.50% fee per side, GST/slippage included | +12.20% | -7.29% | 1.49 | 106 | 0.000 |

These are development backtests, not earned profit. The lab's robustness gate passes both, but the stress profit factor is below the paper benchmark of 1.5. The simulator still lacks the engine's aggregate exposure/portfolio expected-shortfall veto and checks loss switches at candle close. A replay without trades cannot establish order-path parity. Historical holdouts must not be silently reused as new untouched evidence after this modeling correction.

The corrected seven-day replay covers **2026-11-17 00:15 UTC to 2026-11-24 00:15 UTC**: zero fills, zero open positions, simulated equity unchanged at $113.60. It is a cached-data engine exercise, not live forward evidence.

## Current weighted audit

| Domain | Weight | Score / 10 | Evidence and missing verification |
|---|---:|---:|---|
| Quantitative strategy quality | 10% | 3 | Corrected backtests; DSR zero; no adequate forward sample |
| AI / machine learning | 8% | 4 | Tested challenger rejection pipeline; no demonstrated ML advantage |
| Market data quality | 8% | 4 | Feed/closed-candle tests; cached data and known outage; current 99.9% coverage not proven |
| Backtesting and statistics | 12% | 5 | Lot/minimum regression and full reruns; missing portfolio parity/fresh holdout |
| Risk management | 15% | 7 | Passing risk, ES, stop-recovery and kill-switch tests; no live-money drill |
| Execution reliability | 10% | 4 | Offline failure drills and recorded testnet run; no spot adapter |
| Portfolio management | 5% | 4 | Tested ES/exposure veto; limited diversification and allocation |
| Security | 7% | 5 | Secret/network test isolation, restore preflight, live gate; key scope and fresh dependency scan not verified |
| Regulatory and tax | 5% | 0 | No professional confirmation in this audit; estimates are not certification |
| Infrastructure | 5% | 5 | Backup/recovery tests; PC sleep/power risk, same-disk backups, Docker unbuilt |
| Testing and verification | 5% | 7 | Python/frontend checks pass; no browser or container E2E |
| Monitoring and analytics | 3% | 5 | Heartbeat/health regressions; shared outside check can mask one failed bot |
| User interface | 2% | 6 | Unit/type/build checks and accounting-halt API visibility; no browser verification |
| Cost efficiency | 3% | 5 | No paid services added; no fresh cost benchmark (testless-domain cap) |
| Documentation | 2% | 5 | Current caveats reconciled; historical reports retained; testless-domain cap |
| **Weighted total** | **100%** | **4.66 → 4.7** | Independent reviewer checked arithmetic and testless-domain caps |

## Remaining work and activation

1. No verified spot venue/adapter with exchange-side stops and suitable key scope. Delta is perpetual-only; this audit does not authorize derivatives or real orders.
2. Insufficient forward trades/regimes and uptime evidence. The readiness scorer's 60-day/300-trade gate is stricter than the master prompt's 30-day/100-trade benchmark; retain the stricter gate.
3. Professional tax/exchange eligibility confirmation is missing.
4. Docker build/soak, always-on deployment, off-device recovery and distinct per-bot outside monitors remain unverified.
5. API settings construction still mutates process-wide environment (`sources.run_cfg`), a concurrent-read isolation issue. CI enforcement is absent. Deferred; neither is a reason to permit live trading.
6. Exactly-once durable fill/accounting recovery is not implemented. A persisted accounting halt deliberately requires operator reconciliation; do not clear it merely to resume trading.

The running processes retain their already-loaded code. These fixes need a controlled restart to take effect; no restart or deployment was performed. No commit or push was made. The master prompt remains unchanged, and the 9/10 objective stays unmet because required external/forward evidence is missing.

---

## Historical audit — retained for provenance (not current)

The following scores/results predate the modeling and reliability findings above.

**Decision: NOT READY for live capital. Paper trading only.**
Weighted score **5.8 / 10** (4.4 on 2026-11-24, 5.2 on the morning of 11-26, 5.7 after the testnet pass). Readiness scorer (`python -m bot.readiness`): **56/100, DEVELOPMENT ONLY** (was 43, then 50, then 53 after the testnet pass; 56 once heartbeat pings were delivered).
A high score could never override the blockers below. 9/10 is not reachable by code alone (see the last section).

## What was run (2026-11-26)

| Check | Result |
|---|---|
| `python -m pytest -q` (run by the readiness scorer) | **236 passed** (230, then 233 with the testnet-report tests, then 236 with the 5-minute heartbeat tests) |
| Daily backup task `IndiaCryptoBot-backup` (2026-11-27) | registered (09:00 daily, `bot.backup --drill`); first run exit 0, drill passed, row counts match |
| Outside heartbeat (2026-11-27) | `HEARTBEAT_URL` set; both bots delivered pings (0 failures), now every 5 minutes |
| `testnet-check` on the Delta India testnet (2026-11-27) | **11/11 passed**, cleanup OK, account left flat; saved in `reports/testnet_check.json` |
| Frontend `npm test` / `npm run typecheck` | 23 passed / 0 errors (before the morning merge; frontend unchanged since) |
| `python -m bot.readiness` | 56/100, DEVELOPMENT ONLY, state PAPER (50 before the testnet pass, 53 before the heartbeat) |
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
2. ~~`DeltaBroker` has never run against a real API~~ **Resolved for the testnet on 2026-11-27:** `testnet-check` passed all 11 steps on the Delta India testnet (entry, exchange-side stop, cancel, stop re-placed on restart, orphan flattened), saved in `reports/testnet_check.json`. Futures only; the spot blocker above still stands.
3. **No forward evidence:** 0 paper trades, 0 shadow intents.
4. **Legal and tax assumptions unverified** (COMPLIANCE.md).
5. ~~Exposed production credentials~~ **Reported deleted by the owner on 2026-11-27** (exchange-side; cannot be verified from this machine). `I_UNDERSTAND_LIVE_RISK` confirmed cleared in `.env` and not set in the Windows environment.

## Weighted scores (0-10; evidence or the score stays low)

| Domain | Weight | 11-24 | 11-26 am | **now (11-27)** | Evidence and what is missing |
|---|---:|---:|---:|---:|---|
| Quantitative strategy quality | 10% | 6 | 6 | **5** | Gate passed, holdout PF 1.87. **New negative evidence:** deflated Sharpe 0.000 (all trials) / 0.780 (trend family), so the edge is not yet distinguishable from selection luck; trails buy-and-hold on return; no forward trades |
| AI / machine learning | 8% | 3 | 3 | **4** | Champion-challenger pipeline built and tested; first logged decision (4 challengers rejected, reasons and trial count recorded). No AI model beats the no-model baseline |
| Market data quality | 8% | 5 | 5 | **5** | Validation and multi-host retry; failed candles now retried. Coverage not yet re-measured; signal source differs from execution venue |
| Backtesting & statistical validation | 12% | 6 | 7 | **8** | Walk-forward, Monte Carlo, sub-periods, neighbours, fee stress, true holdout, and now a deflated Sharpe with a conservative trial count; reruns reproduce exactly. Missing: >= 300 out-of-sample trades |
| Risk management | 15% | 5 | 7 | **8** | Added: correlation-aware 1-day 97.5% expected-shortfall cap (2% of equity, policy ceiling, fail-closed) and gross-exposure cap in the engine, 12 tests. At current sizing the ES cap is a backstop (worst pair 0.77%). Not verified on a real exchange |
| Execution reliability | 10% | 3 | 3 | **4** | Delta connector verified on the India testnet (11/11: orders, exchange-side stop, restart recovery, orphan flatten), recorded and re-checked by readiness. No spot adapter |
| Portfolio management | 5% | 3 | 3 | **4** | Entries now see the joint, correlated risk of what is already held; no allocation or rebalancing |
| Security | 7% | 4 | 4 | **6** | `pip-audit` clean on requirements and venv; heartbeat URL handled as a secret (tested); leaked production keys reported deleted by the owner and the live-risk flag cleared (11-27). No IP-whitelisted, trade-only key verified yet |
| Regulatory & tax | 5% | 2 | 2 | **2** | Unchanged |
| Infrastructure & reliability | 5% | 3 | 4 | **6** | Keep-awake, same-candle retry, consistent backups; daily scheduled backup with a restore drill every run (first run passed, 11-27). Docker unbuilt; single PC; backups stay on the same disk |
| Testing & verification | 5% | 6 | 7 | **7** | 236 Python + 23 frontend tests. No property-based, chaos or end-to-end browser tests |
| Monitoring & analytics | 3% | 3 | 5 | **6** | External heartbeat configured and delivering (11-27): pings every 5 min, stop after a skipped candle; suggested monitor 5/7 min. Both bots share one check, so one dead bot can be masked by the other |
| User interface | 2% | 0 | 7 | **7** | Read-only dashboard (self-scored 7.8/10) |
| Cost efficiency | 3% | 7 | 7 | **7** | Zero paid services |
| Documentation | 2% | 6 | 7 | **7** | Reports kept current with the code |
| **Weighted total** | 100% | **4.4** | **5.2** | **5.8** | (5.6 code fixes; 5.7 testnet pass; 5.8 after keys, heartbeat and backup task on 11-27) |

## Biggest findings
1. **Selection bias is real.** After counting the 97 strategy settings tried, the ensemble's backtest Sharpe (1.16/yr) is below what the luckiest skill-less strategy would show. Even within the trend family the deflated Sharpe is 0.78, short of 0.95. Only forward paper trades can settle this.
2. **The bot has not traded yet** (0 paper fills, 0 shadow intents, 0 trades in a 60-day replay).
3. **The three coins move together** (daily correlation 0.85-0.90): holding two positions gives little diversification. The new ES cap counts this.
4. **No challenger beats the champion.** Donchian comes closest (better PF, lower return) but has no holdout of its own.

## Why 9/10 is out of reach now, and what moves it
The overall score is capped at 6 until the paper benchmark is met, and the remaining low areas need things only the user or time can provide:

| Needs | Moves |
|---|---|
| ~~Delete the leaked Delta production keys~~, testnet key, `testnet-check`, `HEARTBEAT_URL`, daily backup task: **done 11-27** | Security, Monitoring, Infrastructure |
| Choose a spot venue with an exchange-side stop order, then build its adapter | Execution (largest gap) |
| Chartered-accountant confirmation of tax and TDS | Regulatory |
| 30-90 days of paper and shadow trading on an always-on machine (VPS) | Strategy quality, benchmark cap, uptime |
| Copy `backups\` off this PC weekly (OneDrive or USB) | Infrastructure |
