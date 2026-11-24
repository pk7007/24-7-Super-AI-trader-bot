# Master checklist (resumable by another agent)

Legend: [x] done and verified (tests/evidence) - [~] partial - [ ] not done - [!] blocked.

## Deployment gates (master prompt section 38)
- [~] 1 Architecture approved - documented (ARCHITECTURE.md), not reviewed by you
- [~] 2 Data quality verified - candle validation + Binance cross-check; Delta feed rejected
- [~] 3 Financial calculations verified - 48 tests (sizing, fees, PnL, ledger); no exchange reconciliation
- [~] 4 Strategy research completed - 4 families + ML + mean reversion tested; stat-arb/news/on-chain not
- [x] 5 Historical backtesting completed - BACKTEST_REPORT.md
- [ ] 6 Independent out-of-sample test - no untouched holdout left
- [~] 7 Stress testing - fee stress done; crash/outage/depeg simulations not done
- [ ] 8 Security and compliance - see SECURITY.md, COMPLIANCE.md
- [~] 9 Real-time paper trading - running since 2026-11-24 (needs 30-90 days)
- [ ] 10 Shadow trading
- [ ] 11-14 Manual live authorization, controlled capital, monitoring, scaling

## A-Z domains (status, evidence)
- A Architecture: [~] modular, single process; no service split/API
- B Backtesting: [x] costs, stop-first rule, walk-forward, MC; [ ] purged CV, deflated Sharpe
- C Capital & cost: [x] feasibility report; [x] min-order refusal (tested)
- D Data: [x] validation + provenance in CSV; [ ] WebSocket gaps, survivorship, licensing review
- E Execution: [x] paper; [!] live Delta untested; [ ] spot connector; [ ] order state machine/idempotency keys
- F Financial accounting: [x] ledger CSV+SQLite (tested); [ ] FIFO lots, exchange reconciliation
- G Governance: [x] paper default, live consent flags (tested); [ ] approval workflow for model promotion
- H High availability: [~] reconcile on restart (tested on simulator); [ ] backups, soak test
- I Intelligence/agents: [~] deterministic services only; no LLM agents (by design)
- J Journaling: [x] logs + ledger + state.db
- K Kill switches: [x] daily 3% (tested, survives restart); [ ] weekly/monthly; [ ] manual UI switch
- L Liquidity/latency/slippage: [~] fixed slippage; [ ] depth/spread model
- M ML monitoring: [ ] drift, calibration, registry
- N News: [ ]   O On-chain/order book: [ ]
- P Portfolio & paper: [~] 3 slots; paper running
- Q Quant validity: [~] gate + MC; selection bias acknowledged
- R Risk & regulatory: [~] limits partial; [ ] compliance verified
- S Security & robustness: [~] secrets tests; [ ] scanning/MFA
- T Testing/tax/reconciliation: [x] 48 tests; [~] tax estimates only
- U UI: [ ] dashboard   V Volatility/regime: [~] ATR sizing; [ ] regime agent
- W Walk-forward: [x] (for ML) / rule strategies use fixed parameters; [ ] WebSocket reliability (REST polling)
- X Extreme scenarios: [ ] crash/outage simulations
- Y Yield/risk-adjusted: [x] PF, DD, MC; [ ] Sharpe/Sortino/Calmar/VaR/ES reporting
- Z Zero-trust/production readiness: [ ] not production ready

## Next actions (priority order)
1. P0 rotate exposed Delta keys; never reuse them.
2. P0 decide spot venue; verify its fees, minimums, API and eligibility (official docs) -> build connector.
3. P1 weekly/monthly loss limits, exposure/correlation caps, daily limit to ~1% and re-run the lab.
4. P1 30-90 days paper; shadow trading; weekly `report`.
5. P2 verified tax/TDS config; FY export. P2 backups, heartbeat, Docker build + soak.
6. P3 holdout protocol; deflated Sharpe; purged CV before any new ML.
7. P4/P5 dashboard, regime agent, stress scenarios.
