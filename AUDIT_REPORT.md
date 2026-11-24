# Audit report - 2026-11-24 (supersedes the interim `AUDIT.md`, kept for history)

**Decision: NOT READY for live capital. Paper trading only.**
Weighted score **4.4 / 10**, and a high score could never override the blockers below.

## Blockers (any one blocks live trading)
1. **No spot execution path exists.** The only live broker is Delta *perpetuals*, which the spot-only default forbids; no spot connector is built. Research ([EXCHANGE_RESEARCH.md](EXCHANGE_RESEARCH.md)) found CoinDCX spot has **no documented exchange-side stop order, no sandbox, and no documented trade-only/no-withdrawal key scope** - so RULE 2 and SECURITY rule 7 cannot be met there as documented.
2. **`DeltaBroker` has never run against a real API** (testnet check blocked: needs a key from `demo.delta.exchange`).
3. **No forward evidence.** 3.6 years of backtests and ~hours of paper trading; the master prompt requires 30-90 days of paper plus shadow trading.
4. **Legal/tax assumptions unverified** (COMPLIANCE.md) and exchange eligibility for an Indian resident not established.
5. **Exposed credentials during development** (SECURITY.md): rotate/delete.

## Weighted scores (0-10; evidence in the linked files)

| Domain | Weight | Score | Why |
|---|---:|---:|---|
| Quantitative strategy quality | 10% | 6 | Ensemble passes a strict gate incl. 2.5x fee stress; selection bias, no forward data |
| AI / machine learning | 8% | 3 | The one ML model was honestly rejected; no calibration, drift, MLOps, uncertainty |
| Market data quality | 8% | 5 | Candle validation found a corrupt feed; no WebSocket/sequence checks, no survivorship handling, single source |
| Backtesting & statistical validation | 12% | 6 | Walk-forward, Monte Carlo, sub-periods, parameter neighbours, fee stress; no purged CV, no deflated Sharpe, no holdout |
| Risk management | 15% | 5 | Tested core limits + kill-switch + exchange stops; missing weekly/monthly, VaR/ES, correlation and exposure caps; daily limit 3% vs prompt ~1% |
| Execution reliability | 10% | 3 | Paper broker + reconcile logic tested on a simulator; live untested; no full order state machine |
| Portfolio management | 5% | 3 | 3 positions, per-trade risk; no allocation/rebalancing/correlation |
| Security | 7% | 4 | Secret hygiene + consent gates tested; no MFA/RBAC/scanning; incidents logged |
| Regulatory & tax | 5% | 2 | Estimates only, unverified |
| Infrastructure & reliability | 5% | 3 | Reconcile on restart; Docker unbuilt; single PC; no backups/heartbeat |
| Testing & verification | 5% | 6 | 48 tests on financial invariants; no property-based/chaos/integration |
| Monitoring & analytics | 3% | 3 | Ledger, report, logs; no dashboards/alerts on silence |
| User interface | 2% | 0 | CLI only |
| Cost efficiency | 3% | 7 | Zero paid services; benefit unproven |
| Documentation | 2% | 6 | Accurate and candid; written this session |
| **Weighted total** | 100% | **4.4** | |

## Master checklist coverage
`MASTER_CHECKLIST.md` lists the A-Z domains and 14 gates with real status. It contains **fewer than the 200 criteria requested**: most criteria belong to modules that do not exist (news, sentiment, on-chain, order book, regime, drift, dashboard, FastAPI/Postgres), and padding them would invent evidence. Each is recorded as one "not built" item.

## What a fair path to 9/10 needs
Spot connector + testnet/sandbox verification; 30-90 days of paper including shadow trading; weekly/monthly limits, exposure and correlation caps; verified legal/tax configuration; backups, heartbeat and a Docker soak test; a holdout period never used for selection; then a small, manually authorised live pilot.
