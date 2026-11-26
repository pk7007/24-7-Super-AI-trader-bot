# Changelog (no Git commits exist yet; this is the manual history)

## 2026-11-27 (testnet verification recorded)
* `testnet-check` passed all 11 steps on the Delta India testnet (market entry, exchange-side stop resting, cancel, reconcile re-places a missing stop, orphan position flattened, fills). Test account left flat.
* `bot/testnet_check.py` now saves every run, pass or fail, to `reports/testnet_check.json` (steps, evidence, endpoint, time; never keys or error text). `bot/readiness.py` credits "testnet order test" only for a full passing run against the testnet address in the last 30 days. 3 tests; 233 pass.
* Readiness 50 -> 53/100 (DEVELOPMENT ONLY); audit 5.6 -> 5.7/10 (execution 3 -> 4). Futures only: the spot execution blocker stands.

## 2026-11-26 (audit code fixes: audit 5.2 -> 5.6, readiness 43 -> 50)
* Risk: `bot/portfolio_risk.py` blocks an entry when the portfolio's 1-day 97.5% historical expected shortfall (joint daily returns, so correlation counts) would exceed `max_es_pct` (2%, new policy ceiling, env can only tighten), or when gross exposure would exceed `max_leverage` x equity. Fail-closed on missing history (replay only warns). Uses closed daily candles only (`Feed.daily_closes`). On live data the cap does not bind at current sizing (worst pair 0.77% of equity); coin correlations are 0.85-0.90.
* Backtesting: `bot/stats.py` deflated Sharpe ratio (Bailey & Lopez de Prado; matches the paper's worked example). The lab adds it to every report, counting every setting in every lab report as a trial. FINDING: ensemble DSR 0.000 over 97 trials, 0.780 within the trend family; bar 0.95. Lab reruns reproduced the ensemble exactly (+21.8%/PF 2.5; +15.9%/PF 2.1 at 0.50% fees).
* AI/ML: `bot/experiments.py` champion-challenger log (`reports/experiments.md`): a challenger is only proposed if it passes the gate and beats the champion at 0.10% and 0.50% fees and has its own holdout; switching needs 30 days in shadow and the user's approval. First run: all 4 challengers rejected.
* Infrastructure: `bot/backup.py` (consistent SQLite online backup while bots run, SHA-256 manifest, integrity check, restore only into an empty folder, rotation; never `.env`); `--drill` passed on real state. `backups/` gitignored.
* Monitoring: `bot/heartbeat.py` optional outside heartbeat (`HEARTBEAT_URL`, https only, URL never logged or stored), pinged after each processed candle. Not configured yet.
* Security: `pip-audit` installed in the venv; no known vulnerabilities in `requirements.txt` or the venv.
* Readiness scorer: the ES/exposure, deflated-Sharpe, champion-challenger, backup and heartbeat items now pass only on real evidence (named tests plus a current result), not on a file existing. 230 tests pass. Bots restarted to load the code (no positions, state kept).

## 2026-11-26 (uptime fix)
* FINDING (full audit, AUDIT_REPORT.md 5.2/10): the bots processed only about 70% of candles. Log gaps showed about 90% of the loss was Windows idle sleep (silent stretches of 10 h and 7 h); the rest were network failures, where a failed candle was dropped until the next one.
* Added `bot/keepawake.py`: while a bot runs it asks Windows not to idle-sleep (`SetThreadExecutionState`, system only, the screen may still turn off). It ends with the process, closing the lid still sleeps the PC, `KEEP_AWAKE=0` turns it off, and it does nothing on Linux.
* `bot/main.py`: a failed candle step is now retried on the same candle after 30, 60, 120 and 240 s, stopping 60 s before the next candle, with resting stops and the kill-switch still checked while waiting. Retries are safe because a step skips coins already held and re-checks every limit. Attempts log as "step attempt N failed"; only a candle that is really lost logs "step failed after N attempts" and sends one alert, so `bot/alerts.py` and the dashboard keep counting lost candles only.
* 7 tests in `tests/test_uptime.py`; 198 tests pass. The paper and shadow bots were restarted to load the fix (no positions open, state kept). The new uptime has not been measured yet.

## 2026-11-26 (AI Trade Labs dashboard)
* Added `bot/api/` (FastAPI, `python -m bot.api`): read-only, GET-only, 127.0.0.1, 15 endpoints over the bots' own files; schema-versioned envelope, `null` for missing data, CSP and security headers, safe errors. 21 tests, including "never writes bot state" and "no secret values in responses".
* Added `frontend/` (React 19 + TypeScript strict, Vite, TanStack Query, lightweight-charts): 15 pages from real data only (no order entry, no settings that reach the bots), dark/light themes, responsive to 390 px. 23 unit tests. Agent Monitor and Execution Monitor omitted: no data exists for them.
* FINDINGS: both bots logged 56 of 96 candles in 24 h with 10 step failures (PC sleep, restarts, Binance network errors); the first API draft overstated three protections as live-verified (replaced by an honest `verified_by`, tested); two colour tokens failed WCAG contrast (fixed).
* Reports: FRONTEND_AUDIT, FRONTEND_ARCHITECTURE, DESIGN_SYSTEM, FRONTEND_API_CONTRACT, FRONTEND_QA_REPORT, FRONTEND_SCORECARD (interface 7.8/10; trading readiness unchanged at 43/100). `requirements.txt` gains fastapi, uvicorn, httpx; `.gitignore` gains `frontend/node_modules`, `frontend/dist`. 191 Python tests pass.

## 2026-11-25 (crypto-budget skill)
* Added `bot/budget.py` + a local (uncommitted) skill file for `crypto-budget`: the bot's own size for a coin and stop (or `--bot`: live ticker + the ensemble's ATR stop), each limit's maximum and which one decided, USD and INR, capital needed for the Rs 100 minimum, and the chained `crypto-risk` verdict. `--write` saves `proposals/<mode>_order.json` only on PASS. 30 tests.
* FIX in `crypto-risk`: position size from state.db is in engine units (lot steps), now converted to coins (`coin_units`); new `total_exposure` check (this order + open positions <= 1x equity on spot); equity = cash + open positions at their stops (conservative).
* FINDING: with 2-ATR stops 9-12% away, a 0.5% risk budget buys $4-6 per trade (about 4-5% of a $113.60 account). Not changed; it is the strategy's design and the main reason returns are small. 167 tests pass.

## 2026-11-25 (bots made durable)
* Re-created scheduled tasks `IndiaCryptoBot-paper` / `-shadow` (user's go-ahead): at logon + every 10 min, via new `deploy/start_bot_hidden.vbs` (hidden window; skips if that bot is already running). Bots handed over to the tasks at 21:52 and both reconciled; neither is now a child of the app.
* Found: both bots missed 07:15-17:12 because the PC slept (Kernel-Power 42 "Button or Lid" at 07:17, resumed 17:12). The tasks do not prevent sleep; see DEPLOYMENT.md.

## 2026-11-25 (sizing counts costs)
* FIX: `bot/risk.position_units` now sizes so a full stop-out loses at most `risk_per_trade` INCLUDING round-trip fees, GST and slippage (was stop distance only: ~0.53% real loss vs the 0.5% policy). Used by the engine and the backtest; `feasibility` uses the same formula. `round_trip_cost_pct` moved to `bot/risk.py` and is shared with `bot/riskcheck.py`, so the bot and the check cannot disagree. New test: bot-sized orders PASS the risk check at 0.5-8% ATR. 137 tests pass.
* Re-ran base + fee stress + holdout (holdout as a labelled second look). Base: +21.8%, DD -4.7%, PF 2.50, 83 trades (was +22.5% / -4.9% / 2.44 / 85). All runs pass the gate. Details and old/new table in `BACKTEST_REPORT.md`; pre-fix files in `reports/pre_cost_sizing/`. Readiness unchanged at 43/100.
* Bots found STOPPED at 06:25 IST: last candle 06:00, the 06:15 candle missed, no exit line from the launcher (killed from outside, most likely when the app session that started them restarted). Restarted 06:27 with the new sizing and the feed-review fixes; both reconciled, in cash. Bots started from an app session are not durable: a scheduled task or the 24/7 server is the fix.

## 2026-11-25 (crypto-risk skill)
* Added `bot/riskcheck.py` + a local (uncommitted) skill file for `crypto-risk`: read-only PASS/BLOCK verdict for a proposed order (exit 0 PASS / 20 BLOCK) against the policy the bot enforces, plus "max size and which limit decided it". Fails closed on missing/corrupt state, garbled kill-switch values, bad settings, or an `--equity` what-if above real equity. 44 tests in `tests/test_riskcheck.py`.
* Review (`ecc:silent-failure-hunter`): first pass found P1 holes (an exit with no size passed; a garbled kill-switch value read as clear; `--equity` could raise limits; `BTC/INR` matched BTC; a settings error crashed instead of blocking). All fixed with tests; re-review "open P0/P1: NO".
* FINDING (not changed, user decision): the engine sizes from stop distance only, so a full stop-out of a bot-sized trade loses ~0.53% of equity once fees + slippage are counted, above the 0.5% policy. The risk check counts costs, so it BLOCKs such an order. Fixing the engine changes every backtest.

## 2026-11-24 (master-prompt pass)
* Added spot long-only 1x profile as the **default** (`MARKET=spot`); perps opt-in.
* Added minimum-order refusal, spot lot steps, TDS/notional metrics, `feasibility` command.
* Lab re-run under spot rules and 2.5x fee stress; ensemble/Donchian/trend pass, momentum fails.
* Paper bot moved to spot ensemble run 2 (old perp run archived).
* Wrote ARCHITECTURE, AUDIT_REPORT, BACKTEST_REPORT, COMPLIANCE, COST_ANALYSIS, DEPLOYMENT, DISASTER_RECOVERY, KNOWN_LIMITATIONS, MASTER_CHECKLIST, MODEL_EVALUATION, PAPER_TRADING_REPORT, RISK_MANAGEMENT, SECURITY, STRATEGY_RESEARCH, TAX_REPORTING, API_DOCUMENTATION, DEVELOPMENT_ROADMAP. Tests: 48 passing.

## 2026-11-24 (loss limits)
* Added weekly (6%) and monthly (10%) loss limits next to the daily 3% kill-switch, in the engine and the backtest. Limits are my assumptions, overridable via `DAILY_/WEEKLY_/MONTHLY_LOSS_LIMIT`. Persisted in SQLite, tested (49 tests pass).
* Lab re-run: ensemble unchanged at defaults (+101.5%, DD -14.4%), so the limits did not bind. With tight 2%/3% limits it fell to +72%, DD -10.5%, which shows the wiring works and what a stricter limit costs.
* The running paper bot still uses the old code until it is restarted.

## 2026-11-24 (readiness score, state machine, policy defaults)
* Risk defaults now follow the 2nd master prompt: 0.5% risk per trade, daily 1% / weekly 3% / monthly 5% limits (env-overridable). CORRECTION: the lab's SLOW profile had hardcoded 1% risk and 3 positions, so `reports/lab_spot_strict.json` (+65.3%, DD -9.3%) was really 1% risk, not 0.5%. See the drawdown entry below.
* Added `bot/readiness.py`: evidence-checked 100-point score (missing evidence = 0), mandatory live blockers, and the deployment state machine (no skipped stages, human approver required for live stages). `python -m bot.readiness` writes `reports/readiness.json` and `LIVE_TRADING_READINESS.md`. First score: **37/100, DEVELOPMENT ONLY** (later 40 after the drawdown fix, 42 after fee stress, 43 after the holdout). 53 tests pass.
* Paper bot restarted again to pick up the new limits (still in cash).

## 2026-11-24 (shadow mode)
* Added `python -m bot.main shadow` (`bot/broker/shadow.py`): live public data, same engine and risk checks, order intentions logged to `state/shadow/shadow_intents.csv` with reference price, modelled fill and latency after candle close. No credentials, no network order code; refuses any mode but `shadow`. Readiness now counts shadow days (14 required) as a blocker. 54 tests pass. Started; day 0 of 14.
* Limitation: fills are modelled from public last price plus slippage, since no spot venue order book is integrated. It adds intent logging and isolation over paper, not independent exchange evidence.

## 2026-11-24 (drawdown fix)
* Bug: `bot/lab.py` profiles overrode `risk_per_trade` and `max_positions`. Lab now takes the lower of profile and configured policy (like leverage). Earlier lab results (e.g. +101.5%) were at 1% risk, 3 positions, 3% daily limit.
* True policy backtest (spot, 0.5% risk, daily/weekly/monthly 1/3/5%, ensemble, Binance data, 0.10% fee): 3 positions +28.5%, DD -5.1%, PF 2.69; **2 positions (new default, per policy 1-2) +22.5%, DD -4.9%, PF 2.44**; 1 position +12.0%, DD -3.1%, P(loss) 10%. Three variants tried. Drawdown is under the 8% target; returns are modest (about 6% a year).
* Default `max_positions` is now 2. `reports/lab_spot_policy_mp{1,2,3}.json`.

## 2026-11-24 (fee stress)
* Ensemble under policy limits passes the lab gate at 1x, 1.5x, 2x, 3x and 5x fees (return +22.5% -> +16.8%, DD -4.9% -> -6.0%). Slippage not scaled. Table in BACKTEST_REPORT.md. Readiness item added.

## 2026-11-24 (holdout)
* Pre-registered holdout on 2021-2022 Binance data, never used for tuning ([HOLDOUT_PROTOCOL.md](HOLDOUT_PROTOCOL.md)): **PASS**. +5.3%, DD -5.5%, PF 1.87, 40 trades, while BTC buy-and-hold was -61%. Low return, small sample. Details in BACKTEST_REPORT.md.

## 2026-11-24 (risk-auditor findings fixed)
* Independent `risk-auditor` (first operational run) found two P1s; both fixed with tests (56 pass):
  - Env overrides could loosen policy (e.g. `RISK_PER_TRADE=0.05`, `WEEKLY_LOSS_LIMIT=1.0`). `Settings.from_env` now refuses to start unless 0 < value <= ceiling (risk 0.5%, 2 positions, daily 3%, weekly 3%, monthly 5%). Stricter is allowed.
  - A kill-switch flatten that failed was never retried. The halt is now persisted first and flattening is retried every tick while halted with positions.
* Open (P2/P3, not fixed): backtest checks limits only at candle close (engine checks ~every 20 s), so the backtest trips less often than live; a mid-week upgrade re-bases weekly/monthly limits; the weekly test calls `roll` directly; no backtest test for weekly/monthly.

## 2026-11-24 (persistent bots)
* Paper and shadow bots now run as Windows scheduled tasks (`IndiaCryptoBot-paper`, `IndiaCryptoBot-shadow`) via `run_bot.cmd`: at logon, hidden, restart on failure, no time limit. Added a single-instance lock per mode (`bot.main.single_instance`), tested and verified live (a second paper bot was refused). 57 tests pass.
* Not done: running before login (needs administrator), keeping the PC awake, external heartbeat alert.

## 2026-11-24 (24/7 server package)
* `docker-compose.yml` rewritten: `paper` and `shadow` services, `restart: unless-stopped`, per-mode heartbeat health checks, log rotation, and **no `env_file`** (real keys no longer enter the containers). Added `.dockerignore`, `deploy/setup_vps.sh`, `deploy/make_bundle.sh`; step-by-step server guide in DEPLOYMENT.md.
* Verified: script syntax; bundle has no `.env` or lock files; 57 tests pass from an extracted bundle. **Not verified:** Docker image build (Docker Desktop cannot start here: WSL has no distribution). Not deployed: needs your cloud account.

## 2026-11-24 (readiness-verifier findings)
* `readiness-verifier` (first operational run) found: (1) the scheduled tasks `IndiaCryptoBot-paper/-shadow` no longer exist (they were Running at 19:05; Task Scheduler history is disabled, so the cause is unknown); the bots started by them are still running but will not restart at next logon; (2) about 40% of earned readiness points rested on "word exists in a file" checks.
* Fixed (2): `bot/readiness.py` now runs the full test suite itself and awards risk, reconcile, restart, ledger and reliability points only when the named tests pass; defaults are checked with `enforce_policy(Settings())`; `.env` ignore is checked with `git check-ignore`. Score unchanged at 43/100, now backed by 57 passing tests.
* (1): the user chose to leave the scheduled tasks removed for now; bots keep running until the next restart or logout.

## 2026-11-24 (skills master prompt)
* Added a skills master prompt (kept local, not in this repo): maps the 11 skills of the reference pack (github.com/Jakeschincariol/day-trader-skill, MIT, cloned at `C:\tb\refs\ref`) to 10 crypto skills (build: scanner, time machine, alerts, news read-only, ticket; wrap: risk, budget, exit, signal, report; skip: analyst, Pelosi tracker), a 10-point evidence rubric, author's baseline ratings (0-6, none at 9), and a build-review-rerate loop. Not yet run.

## 2026-11-25 (crypto-alerts skill)
* First skill from [SKILLS_MASTER_PROMPT.md](SKILLS_MASTER_PROMPT.md): `crypto-alerts` (`bot/alerts.py`, a local (uncommitted) skill file for `crypto-alerts`, 23 tests). Read-only; rings once per event on heartbeat loss, step failures, no-data candles, kill-switch, fills, price levels and near-stop; every failed check alerts instead of going silent. `bot/notify.py` `send` now returns delivery success (failed Telegram sends are retried).
* Independent review (`ecc:silent-failure-hunter`): 2 P0 + 4 P1 silent paths found and fixed; re-review: no open P0/P1. Score 8 of 9 applicable points (chain test open). See [SKILLS_AUDIT.md](SKILLS_AUDIT.md). 80 tests pass.
* The live drill found both bots failing 3 candles in a row (Binance `SSLEOFError`, no retry). Retry fix proposed, not applied.

## 2026-11-25 (data feed retry)
* Cause of the lost candles: intermittent `SSLEOFError` connecting to api.binance.com, with no retry, so one dropped connection lost the whole candle (4 in a row on 2026-11-24, 23:15 to 00:00).
* Fix: `bot/data.py` `ResilientExchange` wraps the Binance client (candles, prices, stop checks, history): network errors are retried up to 4 times with 2/5/10 s back-off, rotating api.binance.com -> data-api.binance.vision -> api-gcp.binance.com and keeping the host that works; real errors are not retried; rate limits (418/429) are not retried; each retry is logged; after the last attempt the error is raised so the bot still fails safe and the alert fires. Only the public URL is redirected; markets limited to spot.
* Verified: 8 new tests; live test rotated from a dead host to a working one; both bots restarted 00:32-00:36 and the 00:45 candle succeeded in both (decisions made again).
* Review (`ecc:silent-failure-hunter`): no P0/P1. Applied: rate-limit no-retry, public-only URL, copy/unpickle recursion guard. Open (P2): a lagging mirror or a >500-minute stop window could make a paper stop check pass over unseen candles; no overall time budget per step (worst case about 97 s per call during an outage); candle gaps inside a window are not detected.
* The three review fixes were made after the restart, so the running bots use the earlier version until their next restart (difference only matters during a rate-limit ban).

## Earlier
* Strategy lab + Monte Carlo + promotion gate; ensemble model; venue-price guard; ledger PnL fix; testnet checklist; trend strategy replaced a model with no edge; Binance replaced corrupt Delta candles; core engine with the six rules (reconcile, exchange stops, kill-switch, ledger, secrets).
