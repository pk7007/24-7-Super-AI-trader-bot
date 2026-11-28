# Architecture (updated 2026-11-28)

```
Binance public REST (signals)        Delta India REST (venue price guard; live orders, untested)
        |                                         |
   feeds.LiveFeed / ReplayFeed  ------------>  engine.Engine  <------------  broker: PaperBroker | DeltaBroker
        |                                         |   |   |
   data.validate_candles                strategy/risk  state.db(SQLite)  ledger (CSV + SQLite)
        |                                         |
   TrendModel / EnsembleModel / SignalModel(LightGBM, opt-in)       notify (Telegram, optional)
```

* One async process per mode (`python -m bot.main paper|shadow|live`), candle-driven (15 min), blocking calls via `asyncio.to_thread`.
* **Trust boundary:** the strategy emits probabilities only. `risk.py` + `engine.py` size, gate and place orders. No LLM exists in the system, so none can reach execution.
* **State:** `state/<mode>/state.db` (positions, fills, kill-switch), `paper_exchange.json` (simulated exchange, survives restarts), ledger CSV. Live state lives in `state/` and `trades_ledger.csv`.

## The 21 "agents" from the master prompt: honest status

| # | Agent | Status |
|---|---|---|
| 01 Market data | Built (deterministic): `data.py`, `feeds.py`, candle validation |
| 02 Technical analysis | Partial: EMA, ATR, RSI, Donchian, momentum in `lab.py`/`features.py` |
| 03 Quant research | Built: `lab.py` (candidate comparison, Monte Carlo, promotion gate) |
| 04 Market regime | **Not built** |
| 05 News, 06 Sentiment, 07 On-chain, 08 Order book | **Not built** (deliberately: no evidence they add edge; cost and prompt-injection surface) |
| 09 Strategy selection | Manual: `STRATEGY=` setting; promotion gate is offline |
| 10 Machine learning | Built, **rejected**: LightGBM had rank-IC about 0 |
| 11 Portfolio | Position/exposure limits plus correlation-aware expected-shortfall entry veto in the runtime engine |
| 12 Independent risk | Partial: deterministic limits in `risk.py`/`engine.py` (see RISK_MANAGEMENT.md) |
| 13 Execution | Paper/shadow simulation; Delta perpetual testnet check recorded 2026-11-27; no spot adapter or live-money evidence |
| 14 Backtesting | Built (`backtest.py`, `lab.py`); not a full event-driven order-book simulator |
| 15 Performance analytics | Basic: `report.py` |
| 16 Model drift | **Not built** |
| 17 Compliance | Not built (tax *estimates* only) |
| 18 Cybersecurity | Not built beyond secret handling and tests |
| 19 Infra monitoring | Candle logs, five-minute outside heartbeat, backup drills and successful-candle Docker health logic; image/soak still unverified |
| 20 Red team | This repository's `AUDIT.md` (manual) |
| 21 Cost | Not built; see COST_ANALYSIS.md |

The read-only interface uses FastAPI and React/TypeScript (`bot/api/`, `frontend/`). It binds to localhost and cannot place orders. PostgreSQL/TimescaleDB, Redis, DuckDB/Polars, MLflow/DVC and Prometheus/Grafana are not used.

Protective stops are placed before entry ledger writes. Missing protection is repaired or flattened during reconciliation, candle management and between-candle monitoring. Failed exits retain state/stops until flat is confirmed and block entries while retried. Accounting failures additionally persist a halt across restarts; see KNOWN_LIMITATIONS.md for manual reconciliation requirements.

Execution records now carry stable optional fill IDs. SQLite schema migration adds an indexed identity column; acknowledged stop fills remain queued until durable accounting succeeds. SQLite is authoritative and CSV is regenerated atomically, with historical CSV divergence blocked for manual reconciliation. Risk-period snapshots are transactional; a failed save blocks entries while dirty. Only an end-of-step completion marker can establish successful candle progress.
