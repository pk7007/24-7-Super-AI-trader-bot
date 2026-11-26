# Frontend audit (AI Trade Labs observatory)

Date: 2026-11-25. Scope: what existed before the frontend work, what data is real, and what the UI may and may not show.

## Starting point

* No frontend existed. The only user interfaces were the CLI (`python -m bot.main ...`), log files and Markdown reports.
* No HTTP API existed. Everything the UI needs had to be read from files the bots already write.
* Two bots run 24/7 on this PC (paper, shadow) as Windows scheduled tasks. Live trading does not exist as a running service.

## Real data available (and used)

| Data | Source on disk | Written by | Shown on |
|---|---|---|---|
| Equity, cash | `state/<mode>/paper_exchange.json` | paper/shadow broker | Command Center, Paper, Shadow |
| Positions, fills, kill-switch state | `state/<mode>/state.db` (opened read-only) | engine | Orders, Paper, Shadow, Risk |
| Per-candle decisions, equity, heartbeat | `state/<mode>.log` engine lines | engine | Signals, Market Terminal, Paper/Shadow equity chart, topbar |
| Errors, warnings, restarts | `state/<mode>.log` | engine, main, notify | Event Log, System Health |
| Order intentions | `state/shadow/shadow_intents.csv` | shadow broker | Shadow, Orders (none written yet) |
| Tax ledger | `state/<mode>/trades_ledger.csv` | ledger | Ledger & Tax (none written yet) |
| Candles | Binance public API (live) or `data/*_binance.csv` (cached) | API / `fetch` | Market Terminal |
| Lab and backtest results | `reports/*.json` | `lab`, `backtest` | Strategy Lab, Backtesting |
| Readiness | `reports/readiness.json` + `bot/readiness.py` constants | `readiness` | Live Readiness, topbar |
| Feasibility | `bot/feasibility.build_report` on cached BTC data | API (cached daily) | Capital Feasibility |
| Effective config and ceilings | `bot/config.py` | code | Risk Management |

## Data that does not exist (shown as missing, never invented)

* Signal probabilities or confidence: the running strategy is rule-based and outputs BUY / SELL / stay out only.
* Fills, positions, ledger rows, shadow intents: none yet (no trade has triggered since the bots started).
* CPU / memory / disk, Docker health, exchange connectivity: not collected. Listed under "Not collected" on System Health.
* Live exchange state: Delta Exchange India is not connected. Shown as "not connected".
* Agent telemetry: none exists, so the master prompt's Agent Monitor page was not built.

## Omitted routes and why

| Requested page | Decision |
|---|---|
| Agent Monitor | Omitted: no agent telemetry is recorded anywhere. A page would have to invent it. |
| Execution Monitor | Omitted: no execution venue is connected. Paper fills are on Orders & Positions. |
| Exchange Connections | Folded into System Health as a "Connections" table showing what is and is not connected. |
| Monte Carlo | Folded into Strategy Lab (per-strategy Monte Carlo from the lab reports). |
| Order entry, kill-switch buttons, config editing | Not built by design: the UI is observational only. |

## Findings surfaced by building the UI

1. **Missed candles.** Both bots logged 56 of 96 expected 15-minute candles in the last 24 hours, with 10 step failures (Binance network errors on 2026-11-24 evening) and 7-10 restarts. Cause: PC sleep, app restarts, network errors. Shown on Command Center and System Health.
2. **Protection labels overstated.** The first API version marked three protections `verified_live: true` although no live venue has ever been connected. Replaced with a `verified_by` text ("unit tests + running paper bot", "assumption, not verified", ...) and a test that forbids any live-verification claim.
3. **Policy discrepancy** (already known): configured daily loss 1% vs hard ceiling 3%. Shown as a warning on Risk Management.
4. **Readiness report is stale**: last scored 2026-11-25 00:54 UTC. The page shows its age.
5. **Port conflict**: 127.0.0.1:8765 was taken by another program on this PC (`app.py`, not part of this project). The API has `--port`; testing used 8766.
6. **Cold start**: `/api/v1/markets` takes about 6 s on first call (Binance market load), then about 130 ms.
