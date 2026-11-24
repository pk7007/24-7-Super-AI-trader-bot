# Development roadmap

| Priority | Item | Why | Acceptance |
|---|---|---|---|
| P0 | Rotate exposed keys; trade-only, IP-whitelisted keys | credentials appeared in chat | old keys deleted on exchange |
| P0 | Settle the spot-venue blockers in EXCHANGE_RESEARCH.md: (1) confirm an exchange-side spot stop order exists, (2) verify trade-only/no-withdrawal key scope, (3) read fees/minimums from the official dashboard; only then build `SpotBroker` | CoinDCX docs show no spot stop param, no sandbox | written confirmation per item; other venues (CoinSwitch, Mudrex) evaluated |
| P0 | Verify Indian tax/TDS/eligibility from official sources | all tax numbers are assumptions | CA-signed COMPLIANCE.md |
| P1 | Weekly/monthly loss limits, exposure & correlation caps, strategy-suspension drawdown, daily limit ~1% | master-prompt risk defaults | tests + lab re-run |
| P1 | 30-90 day paper run + shadow trading | no forward evidence | PAPER_TRADING_REPORT.md vs backtest expectation |
| P2 | Backups, heartbeat alert, Docker build + 48 h soak | single PC, silent failure | recovery drill written and timed |
| P2 | Historical INR rates, FY tax export | reporting | reconciles with exchange statements |
| P3 | Untouched holdout, deflated Sharpe, multiple-testing correction | selection bias | documented protocol |
| P3 | Regime filter experiment (only adopt if it improves out-of-sample net results) | chop losses | lab gate |
| P4 | WebSocket feed + order-book spread model | slippage realism | measured vs paper fills |
| P5 | Read-only dashboard (equity, positions, ledger, kill-switch state) | usability | no write path to execution |

Explicitly **not planned** until evidence supports them: LLM/news/sentiment trading, reinforcement learning, HFT/scalping, futures leverage.
