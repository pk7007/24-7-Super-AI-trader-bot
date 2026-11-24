# Changelog (no Git commits exist yet; this is the manual history)

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

## Earlier
* Strategy lab + Monte Carlo + promotion gate; ensemble model; venue-price guard; ledger PnL fix; testnet checklist; trend strategy replaced a model with no edge; Binance replaced corrupt Delta candles; core engine with the six rules (reconcile, exchange stops, kill-switch, ledger, secrets).
