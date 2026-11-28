# Full repository audit — 2026-11-28

**Engineering assessment: 5.1/10 (weighted 5.08). Live readiness: 41/100, DEVELOPMENT ONLY. NO-GO for live money.**

This audit includes the earlier uncommitted fixes and a second, broader audit of the trading, application, deployment and recovery boundaries. The reviewed branch is `audit/full-review-20261128`, based on `e8cb6c6`. Independent reviewers checked each other's changes and the lead's configuration/data/quantitative changes; no open P0/P1 was found in the changed paths after the final corrections. That is a bounded review result, not a guarantee that the system has no defects.

Versioned, credential-free evidence summary: [audits/2026-11-28/verification.json](audits/2026-11-28/verification.json). Detailed local XML/scanner artifacts remain outside Git so runtime records and machine-specific details are not published.

## Verification

| Check | Result | Evidence |
|---|---|---|
| Full Python suite, Windows | **378 passed**, one Starlette/httpx deprecation warning | `reports/full_audit_tests.xml` |
| Full Python suite, Linux container | **378 passed**, same warning; network disabled, no bot state/credentials mounted | `reports/full_audit_linux.xml` |
| Frontend | **25 passed**, TypeScript check and production build passed | `frontend/package.json` commands |
| Dependencies | pip-audit and npm audit: **no known vulnerabilities reported** | `reports/full_audit_pip.json`, `reports/full_audit_npm.json`; does not prove absence of vulnerabilities |
| Packaging | Pinned Python 3.12 base-image digest; project dependency constraints; Docker build and isolated import/health smoke passed | `Dockerfile`, `requirements.lock` |
| Deployment manifest | Compose syntax passed using an empty environment file; no service started | `docker compose --env-file NUL config --quiet` |
| Browser | All **15 routes** render on desktop and 375px mobile, with no page-level horizontal overflow; 768px tablet sample checked; no console errors observed | `reports/full_audit_20261128/summary.json` |
| Accessibility | Settings-page Lighthouse snapshot: **100 accessibility / 100 best practices**, desktop and mobile | Snapshot only, not an all-page WCAG audit; SEO60/agentic50 not launch criteria for a private dashboard |
| Visual/performance limits | No committed screenshot baseline or performance trace | Visual regression/Core Web Vitals remain unverified |
| GitHub automation | Added least-privilege, SHA-pinned Python, frontend and container CI jobs | `.github/workflows/checks.yml`; consult the PR for remote execution status |

Browser/reviewer quota interruptions were temporary; work resumed after the service's stated reset, and the final checks and independent reviews completed.

## Findings fixed

| Boundary | Corrected behavior |
|---|---|
| Order acknowledgments and partial fills | Actual confirmed fill quantity determines protection/state. Zero/missing/unconfirmed execution is not guessed as a full fill. Uncertain entry or exit acknowledgment persists a safety halt and triggers reconciliation rather than silent re-entry |
| Protection | Entry protection precedes accounting; missing stops are repaired or flattened on startup/candle/monitor. Failed emergency exits retain state/stops and block entries until flat is confirmed |
| Risk persistence | Daily/weekly/monthly snapshots commit atomically. A failed save remains dirty and halted across retries; corrupt persisted flags/baselines fail closed |
| Durable execution accounting | Stable execution IDs distinguish partial trades sharing an order. Paper stop fills are peeked and acknowledged only after accounting succeeds. SQLite is authoritative; CSV regeneration is atomic, retriable and idempotent. Divergent historical CSV-only records are preserved and block automatic overwrite |
| Data and settings | NaN/infinite prices, bad OHLC geometry, invalid daily risk bars and invalid portfolio/sizing inputs fail closed. Unknown profile/mode/strategy and misspelled testnet values refuse startup. Observers use isolated settings snapshots and never load dotenv |
| Backups and migration | Restore verifies exact allowlisted contents, hashes, database integrity and account structure before writing. Empty/failed drills fail, retention is validated, valid recovery points survive bad new snapshots. State bundles hold both bot locks while archiving; runbook disables PC launchers before migration |
| Health and forward evidence | Only a success marker emitted at the end of a completed step proves progress; error/diagnostic/no-data log activity cannot manufacture uptime. Completed trades are grouped across partial exits and net of all recorded fees. Future-dated evidence is rejected; nonzero pytest exit cannot become a green score from partial XML |
| API/UI security and accuracy | Strict loopback Host allowlist; credential-pattern log redaction; no process-wide settings mutation; accounting halts visible; full-account aggregates are not truncated to the last1,000 display rows. Historical/unversioned/incomplete research is not labeled current or deployed |
| Research model | Spot lot/minimum gates match the market profile. Drawdown includes initial capital. Slow-strategy holding horizon now matches the shipped 30-day default. Simulation version3 prevents earlier models earning current readiness credit |
| Testnet evidence | Execution-version matching prevents a pre-change adapter test from validating the changed broker. Three historical testnet points are removed; a separately authorized current-adapter test is required |

Runtime strategy and policy ceilings were not loosened. No real or testnet exchange orders were sent.

## Repeated development-data research

Ensemble only, cached 15-minute BTC/ETH/SOL data ending 2026-11-24; $113.60 starting equity, spot, long-only, 1x, current configured risk defaults, GST/slippage included. These are backtests, not earned profit, new out-of-sample results or a fresh holdout.

| Fee per side | Return | Max DD | PF | Trades | Robustness gate |
|---|---:|---:|---:|---:|---|
| 0.10% | +22.03% | -6.77% | 1.80 | 123 | Passed |
| 0.50% stress | +11.41% | -7.02% | 1.42 | 120 | **Failed: only 2/4 positive subperiods** |

The isolated-run DSR numbers exclude earlier trial history and must not be presented as selection-adjusted proof of an edge. The simulator still omits the runtime portfolio ES/aggregate-exposure veto and observes loss switches at candle close. Older holdout/results tables are historical after these modeling corrections. No champion was promoted or runtime parameter changed.

The seven-day full-engine replay had **zero fills, zero open positions, equity $113.60**. It cannot validate a profitable strategy or exercise exchange fills. Outputs: `reports/full_audit_20261128/`; reproduction scripts are local under `C:/tb/scratch/full_audit_research.py` and `full_audit_evidence.py`.

## Weighted assessment

| Domain | Weight | Score/10 | Basis and gap |
|---|---:|---:|---|
| Quantitative strategy quality | 10% | 3 | Fee-stress failure; no adequate forward evidence |
| AI/ML | 8% | 4 | Tested research/rejection pipeline; no demonstrated ML advantage |
| Market data | 8% | 5 | Finite/OHLC/daily-feed regressions; current continuous coverage unproven |
| Backtesting/statistics | 12% | 5 | Model corrections and reproducible reruns; incomplete engine parity/fresh holdout |
| Risk | 15% | 8 | Independent failure/retry/persistence/partial-fill drills; code-tested, not live-validated |
| Execution | 10% | 4 | Offline adapter/fill tests; changed adapter not exchange-validated; no spot adapter |
| Portfolio | 5% | 4 | Tested ES/exposure veto; limited allocation/diversification |
| Security | 7% | 6 | Fresh advisory scans, Host/redaction/restore tests; key permissions unverified |
| Regulatory/tax | 5% | 0 | No professional confirmation; accounting estimates are not certification |
| Infrastructure | 5% | 6 | Actual build/Linux tests and migration/recovery tests; no server/48h soak/off-device drill |
| Testing | 5% | 8 | Windows/Linux suites, frontend checks and browser smoke; no property/chaos/load campaign |
| Monitoring | 3% | 5 | Success-only proof and tests; new code is not loaded by current bot processes |
| Interface | 2% | 7 | Browser routes/responsiveness and unit tests; snapshot accessibility covers Settings only |
| Cost | 3% | 5 | No paid services added; no cost benchmark (testless-domain cap) |
| Documentation | 2% | 5 | Evidence/limitations reconciled; testless-domain cap |
| **Weighted total** | **100%** | **5.08 → 5.1** | Independent reviewer accepted the conservative engineering judgment; overall stays below6 until paper benchmark evidence exists |

## Still blocked

- No verified spot execution adapter with exchange-side stops and appropriate key scope.
- Changed Delta adapter requires a separately authorized testnet validation. Startup trade-history recovery/pagination remains incomplete; exact historical fills cannot be inferred safely after downtime.
- Adequate forward trades, multiple regimes and continuous uptime are absent. Legacy diagnostic logs do not establish the new success-marker-based evidence; zero verified marker-days is not a claim that the old bots never ran.
- Professional tax/exchange eligibility confirmation, 48h container soak, always-on deployment and off-device recovery remain missing.
- The outside monitor is still shared between modes, and the dashboard's settings are an inferred launch profile rather than a verified snapshot from the running processes.
- Persistent accounting halts require operator reconciliation. Stable execution deduplication does not provide exactly-once behavior across every possible exchange acknowledgment failure.

## Activation and rollback

The running paper/shadow bots and their scheduled tasks were inspected but not restarted or changed. They still use already-loaded code. GitHub PR creation and CI do not activate these fixes.

Before any later authorized activation, stop the confirmed mode processes and take a verified recovery snapshot; inspect schema/ledger consistency and preserve the pre-upgrade snapshot. The additive `fill_id` schema migration happens on opening state with the new code. Do not resume an older CSV-first writer against newer state after an incident without reconciling accounting. Rollback requires stopped workers, a selected authoritative snapshot, compatible code and a recovery drill; never run two copies of an account during migration.

The master prompt's 9/10 and paper benchmark exit conditions are unmet. No merge, deployment, live-trading authorization or restart is implied by this report.
