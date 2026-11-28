<div align="center">

# 24/7 Super AI Trader Bot

**A safety-first, 24/7 crypto trading bot for Indian traders, built for Delta Exchange India.**

Rule-based trend strategies · Strict risk limits · Exchange-side stops · Crash recovery · India tax ledger

![Python](https://img.shields.io/badge/python-3.12%2B-3776AB?logo=python&logoColor=white)
![Tests](https://img.shields.io/badge/tests-offline%20suite-2ea44f)
![Mode](https://img.shields.io/badge/default%20mode-paper%20trading-blue)
![Status](https://img.shields.io/badge/live%20trading-not%20ready-red)
![Docker](https://img.shields.io/badge/docker-ready-2496ED?logo=docker&logoColor=white)
![License](https://img.shields.io/badge/license-MIT-yellow)

</div>

---

> [!WARNING]
> **This is research software. It is not ready to trade real money.**
> Every result below comes from backtests, one historical replay and a short stretch of paper trading.
> The Delta perpetual broker has a recorded **testnet check, with no live-money verification**. There is
> **no spot exchange connector yet**. Paper mode is the default and needs no API keys.
> Nothing here is financial advice. Read [KNOWN_LIMITATIONS.md](KNOWN_LIMITATIONS.md) before trusting any number.

> **2026-11-28 audit:** older spot backtest tables below used perpetual lot sizes and omitted the INR minimum-order gate. Both are corrected in code; those tables remain historical. See [AUDIT_REPORT.md](AUDIT_REPORT.md) for current verification and remaining blockers.

> **Full audit update:** 378 Python tests passed on Windows/Linux, 25 frontend tests passed, and the Docker build/browser smoke checks completed. The corrected 30-day-hold ensemble backtested at +22.03% base fees; **the 0.50% fee-stress robustness gate failed**. See [the full report](FULL_AUDIT_2026-11-28.md). Live trading remains blocked.

## Table of contents

- [What it does](#what-it-does)
- [Highlights](#highlights)
- [Results so far](#results-so-far)
- [Quick start](#quick-start)
- [Commands](#commands)
- [Dashboard (read-only)](#dashboard-read-only)
- [Configuration](#configuration)
- [Safety rules](#safety-rules)
- [Architecture](#architecture)
- [Project layout](#project-layout)
- [Running 24/7 with Docker](#running-247-with-docker)
- [Going live (only after testnet)](#going-live-only-after-testnet)
- [Documentation](#documentation)
- [License](#license)
- [Disclaimer](#disclaimer)

## What it does

The bot watches **BTC, ETH and SOL** on 15-minute candles, decides when a trend is worth joining, and
manages each position with a stop-loss and hard daily, weekly and monthly loss limits. It runs around the
clock, survives restarts, and records every fill in a tax-ready ledger.

- **Signals** come from clean Binance USDT candles. Delta India's own candle history failed validation.
- **Orders** are meant for Delta Exchange India.
- **Default profile:** spot, long-only, 1x leverage, `ensemble` strategy. Perpetual futures with shorting are opt-in.

> **About the "AI".** A LightGBM machine-learning model was built and tested honestly. It showed **no
> predictive edge** (rank-IC about 0, -68% in backtest), so it was **rejected**. The default strategy is
> rule-based. The ML model is still in the code and only runs if you opt in with `STRATEGY=ml`.

## Highlights

| | |
|---|---|
| 🧠 **Strategy lab** | Compares candidate strategies under identical costs, runs Monte Carlo resampling, and promotes a strategy only if it passes a strict robustness gate. |
| 📈 **Ensemble trend strategy** | Trades only when an EMA-trend rule and a slower time-series-momentum rule agree. |
| 🛡️ **Layered risk controls** | 0.5% risk per trade, max 2 positions, 1% daily / 3% weekly / 5% monthly loss limits. Loosening them requires a code change, not an env var. |
| 🛑 **Exchange-side stops** | Every entry gets a stop on the exchange. If the stop can't be placed, the position is closed at once. |
| 🔁 **Crash recovery** | On startup, the bot reconciles with the exchange before placing any order. |
| 🧾 **India tax ledger** | Every fill goes to `trades_ledger.csv` and SQLite, with TDS and tax estimates. |
| 👥 **Paper and shadow modes** | Paper simulates fills on live prices. Shadow runs the real risk checks and logs what it *would* order. |
| 🐳 **Deployable** | Docker Compose setup with health checks, plus a VPS setup script. Windows scheduled-task launcher included. |
| 🔔 **Alerts** | Optional Telegram notifications. |

## Results so far

Backtest on Binance 15-minute candles, **April 2023 to November 2026 (3.6 years)**. Spot, long-only, 1x,
fees plus 18% GST and slippage included. Full tables are in [BACKTEST_REPORT.md](BACKTEST_REPORT.md).

| Strategy | Fee per side | Return | Max drawdown | Profit factor | Trades | Gate |
|---|---|---:|---:|---:|---:|:---:|
| **ensemble** | 0.10% | **+101.5%** | -14.4% | 2.72 | 111 | ✅ |
| ensemble | 0.25% (stress) | +95.2% | -15.3% | 2.54 | 114 | ✅ |
| donchian 20d | 0.10% | +81.4% | -15.9% | 2.44 | 84 | ✅ |
| trend EMA 14d | 0.10% | +60.1% | -13.3% | 1.70 | 237 | ✅ |
| momentum 30d | 0.10% | +17.9% | -30.1% | 1.15 | 1202 | ❌ |
| LightGBM ML model | n/a | -68% | n/a | n/a | n/a | ❌ |

Buy-and-hold over the same window: BTC +109%, ETH -10%, SOL +209%.

**Crash test.** In a pre-registered 2021 to 2022 holdout that the strategy was never tuned on, the
ensemble returned **+5.3%** with a -5.5% max drawdown while BTC fell 61%.

**How to read these numbers:**

- The table above used older, looser risk settings. Under today's stricter policy limits the same
  ensemble returns about **+22.5%** over 3.6 years with a **-4.9%** max drawdown.
- Several strategies were compared on the same window, so the winner's return is optimistic (selection bias).
- Most of the gain came from the 2023-24 bull market. The strategy wins about 30% of trades and earns from a few large trends.
- The crash-test return is roughly 3% a year before tax, from only 40 trades. It shows capital protection, not strong returns.

## Quick start

Requires **Python 3.12+** for the verified dependency lock. Paper mode needs no API keys.

```bash
git clone https://github.com/pk7007/24-7-Super-AI-trader-bot.git
cd 24-7-Super-AI-trader-bot

python -m venv venv
venv\Scripts\activate            # Windows
# source venv/bin/activate       # Linux / macOS

pip install -r requirements.txt -c requirements.lock
cp .env.example .env             # Windows: copy .env.example .env

python -m bot.main fetch --days 540     # download public market data
python -m pytest -q                     # run the test suite
python -m bot.main paper                # start 24/7 paper trading
```

## Commands

All commands run as `python -m bot.main <command>`.

| Command | What it does |
|---|---|
| `fetch --days N [--refresh]` | Download and cache candle history (public data, no key). |
| `lab [--only a,b] [--taker 0.0025] [--tag name]` | Compare strategies, run Monte Carlo, apply the promotion gate. |
| `backtest` | Walk-forward, out-of-sample backtest with fees, GST, slippage and funding. |
| `replay --days N` | Run the full engine (stops, kill-switch, ledger) over recent history. |
| `feasibility` | Check which capital levels are economically viable after fees and minimum order sizes. |
| `paper` | 24/7 paper trading on live prices. No real orders. |
| `shadow` | Live data and production risk checks; logs order intentions without sending them. |
| `report --mode paper` | Summarise the ledger for a mode. |
| `python -m bot.backup [--drill]` | Back up every bot's state (safe while running); `--drill` also restores and compares. |
| `python -m bot.experiments` | Log a champion-challenger decision from the latest lab reports (never changes the strategy). |
| `python -m bot.readiness` | Re-score live-trading readiness from evidence (runs the tests). |
| `train --days N` | Fit the optional LightGBM model (only used with `STRATEGY=ml`). |
| `testnet-check` | Step-by-step verification of the Delta broker on testnet. |
| `live` | Real orders on Delta Exchange. Locked behind explicit consent; see below. |

## Dashboard (read-only)

A browser dashboard, **AI Trade Labs**, shows what the bots are doing: equity, positions, fills, per-candle decisions,
loss limits, live candles, strategy and backtest evidence, capital feasibility, tax ledger, health and logs. It only
reads the bots' files; it cannot place orders or change settings, and live trading shows as disabled.

```bash
pip install -r requirements.txt
cd frontend && npm ci && npm run build && cd ..
python -m bot.api                  # open http://127.0.0.1:8765  (use --port 8766 if 8765 is taken)
```

The API listens on 127.0.0.1 only and has no login, so do not expose it to a network. Details:
[FRONTEND_ARCHITECTURE.md](FRONTEND_ARCHITECTURE.md), [FRONTEND_API_CONTRACT.md](FRONTEND_API_CONTRACT.md),
[FRONTEND_SCORECARD.md](FRONTEND_SCORECARD.md) (scores the interface, not trading readiness).

## Configuration

Settings come from `.env` (see [.env.example](.env.example)) and environment variables. **Never commit `.env`.**
It is already in `.gitignore`.

| Variable | Default | Meaning |
|---|---|---|
| `BOT_MODE` | `paper` | `paper`, `shadow` or `live` |
| `STRATEGY` | `trend` | `trend`, `ensemble` (recommended) or `ml` |
| `MARKET` | `spot` | `spot` (long-only, 1x) or `perp` (long/short, up to 2x) |
| `START_EQUITY_USD` | `1000` | Starting balance for paper and shadow |
| `USDT_INR` | `88` | Conversion rate for INR reporting |
| `RISK_PER_TRADE` | `0.005` | Fraction of equity risked per trade (max 0.5%) |
| `MAX_POSITIONS` | `2` | Max open positions (max 2) |
| `DAILY_LOSS_LIMIT` / `WEEKLY_LOSS_LIMIT` / `MONTHLY_LOSS_LIMIT` | `0.01` / `0.03` / `0.05` | Loss limits that halt trading |
| `DELTA_API_KEY` / `DELTA_API_SECRET` | empty | Only needed for `live` |
| `DELTA_TESTNET` | `1` | `1` uses Delta India testnet endpoints |
| `I_UNDERSTAND_LIVE_RISK` | empty | Must be exactly `yes` for live trading |
| `TELEGRAM_BOT_TOKEN` / `TELEGRAM_CHAT_ID` | empty | Optional alerts |

Risk settings can only be made **stricter** through the environment. The bot refuses to start if any
value is looser than the policy ceilings in [`bot/config.py`](bot/config.py).

## Safety rules

These six rules are non-negotiable (full text in [SAFETY_RULES.md](SAFETY_RULES.md)). Each one is enforced in code and covered by tests.

| # | Rule | Enforced in | Tests |
|---|---|---|---|
| 1 | No look-ahead: every feature uses `.shift(1)`, so decisions only see closed candles | `features.py`, `trend.py` | `test_rule1_*` |
| 2 | Exchange-side stop on every entry; flatten if it can't be placed | `engine._enter` | `test_rule2_*` |
| 3 | Reconcile with the exchange before placing any order | `engine.reconcile` | `test_rule3_*` |
| 4 | Daily kill-switch: flatten and halt; survives restarts | `risk.DailyKillSwitch`, `engine.check_killswitch` | `test_rule4_*` |
| 5 | Every fill goes to `trades_ledger.csv` and SQLite | `ledger.py` | `test_rule5_*` |
| 6 | Secrets only from `.env`; live trading needs explicit consent | `config.py`, `broker/delta.py` | `test_rule6_*` |

Other guards: only one bot per mode can run (lock file), stale candles skip the cycle, entries are skipped
if Delta's price differs from the signal feed by more than 0.5%, and orders below the minimum economic
size are refused. Paper, shadow and replay write to `state/<mode>/`, so they can never pollute the real tax ledger.

## Architecture

```
Binance public REST (signals)          Delta India REST (price guard, live orders)
          │                                          │
  feeds.LiveFeed / ReplayFeed ───────────►  engine.Engine  ◄──────── broker: Paper | Shadow | Delta
          │                                  │      │      │
  data.validate_candles              strategy + risk  state.db  ledger (CSV + SQLite)
          │                                  │
  TrendModel / EnsembleModel / SignalModel (LightGBM, opt-in)     notify (Telegram, optional)
```

- **One async process**, driven by 15-minute candles. Stops and the kill-switch are checked between candles.
- **Trust boundary:** the strategy only outputs probabilities. `risk.py` and `engine.py` decide size, apply
  limits and place orders. No LLM is involved anywhere in the trading path.
- **State:** `state/<mode>/state.db` holds positions, fills and the kill-switch. The paper exchange is saved to JSON after every change, so it survives restarts like a real exchange.

More detail in [ARCHITECTURE.md](ARCHITECTURE.md).

## Project layout

```
.
├── bot/
│   ├── main.py            # CLI entry point
│   ├── engine.py          # trading engine (rules 2-4), shared by paper, replay and live
│   ├── strategy.py        # probabilities → trade decisions
│   ├── trend.py           # rule-based EMA trend strategy
│   ├── lab.py             # strategy lab, ensemble model, Monte Carlo, promotion gate
│   ├── model.py           # optional LightGBM signal model
│   ├── features.py        # look-ahead-safe features (rule 1)
│   ├── risk.py            # sizing, stops, kill-switch (rule 4)
│   ├── backtest.py        # walk-forward backtest with realistic costs
│   ├── feasibility.py     # capital viability check
│   ├── readiness.py       # evidence-based live-readiness score
│   ├── ledger.py          # India tax ledger (rule 5)
│   ├── state.py           # SQLite state
│   ├── data.py, feeds.py  # market data download, validation and feeds
│   ├── notify.py          # Telegram alerts
│   ├── api/               # read-only dashboard API (python -m bot.api)
│   └── broker/            # paper, shadow and Delta Exchange brokers
├── frontend/              # AI Trade Labs dashboard (React + TypeScript, Vite)
├── tests/                 # offline regressions, including the safety rules
├── deploy/                # VPS setup and bundle scripts
├── Dockerfile
├── docker-compose.yml     # paper + shadow services with health checks
├── run_bot.cmd            # Windows scheduled-task launcher (paper/shadow only)
└── *.md                   # reports, audits and design docs
```

## Running 24/7 with Docker

```bash
cp .env.example .env
docker compose up -d --build
docker compose logs -f paper
```

The Compose file runs the **paper** and **shadow** services only. It deliberately does not load `.env`,
so exchange keys never enter the containers, and it has no live service. Each service has a health check
that turns unhealthy if no heartbeat is logged for 40 minutes. See [DEPLOYMENT.md](DEPLOYMENT.md) for the
full VPS guide (Mumbai region, UTC).

> The Docker image has not been built and tested yet. Treat this as a starting point.

## Going live (only after testnet)

The bot will not trade real money unless every one of these is in place.

1. On Delta Exchange India, create a **trade-only API key** (no withdrawal permission) and whitelist your server's static IP.
2. In `.env`, set `DELTA_API_KEY`, `DELTA_API_SECRET`, `DELTA_TESTNET=1`, `BOT_MODE=live` and `I_UNDERSTAND_LIVE_RISK=yes`.
3. Run `python -m bot.main testnet-check`, then `python -m bot.main live` on **testnet**. Check entries, stop placement, cancels and flattening.
4. Only after that, consider `DELTA_TESTNET=0` with an amount you can afford to lose.

See [LIVE_TRADING_READINESS.md](LIVE_TRADING_READINESS.md) for the full checklist.

## Documentation

| Topic | Document |
|---|---|
| Rules, limits and caveats | [SAFETY_RULES.md](SAFETY_RULES.md), [KNOWN_LIMITATIONS.md](KNOWN_LIMITATIONS.md), [AUDIT_REPORT.md](AUDIT_REPORT.md) |
| Design | [ARCHITECTURE.md](ARCHITECTURE.md), [API_DOCUMENTATION.md](API_DOCUMENTATION.md) |
| Research | [STRATEGY_RESEARCH.md](STRATEGY_RESEARCH.md), [EXCHANGE_RESEARCH.md](EXCHANGE_RESEARCH.md), [MODEL_EVALUATION.md](MODEL_EVALUATION.md) |
| Results | [BACKTEST_REPORT.md](BACKTEST_REPORT.md), [PAPER_TRADING_REPORT.md](PAPER_TRADING_REPORT.md), [HOLDOUT_PROTOCOL.md](HOLDOUT_PROTOCOL.md) |
| Risk and operations | [RISK_MANAGEMENT.md](RISK_MANAGEMENT.md), [DEPLOYMENT.md](DEPLOYMENT.md), [DISASTER_RECOVERY.md](DISASTER_RECOVERY.md), [SECURITY.md](SECURITY.md) |
| India specifics | [COMPLIANCE.md](COMPLIANCE.md), [TAX_REPORTING.md](TAX_REPORTING.md), [COST_ANALYSIS.md](COST_ANALYSIS.md) |
| Planning | [DEVELOPMENT_ROADMAP.md](DEVELOPMENT_ROADMAP.md), [MASTER_CHECKLIST.md](MASTER_CHECKLIST.md), [CHANGELOG.md](CHANGELOG.md) |
| Dashboard | [FRONTEND_AUDIT.md](FRONTEND_AUDIT.md), [FRONTEND_ARCHITECTURE.md](FRONTEND_ARCHITECTURE.md), [DESIGN_SYSTEM.md](DESIGN_SYSTEM.md), [FRONTEND_API_CONTRACT.md](FRONTEND_API_CONTRACT.md), [FRONTEND_QA_REPORT.md](FRONTEND_QA_REPORT.md), [FRONTEND_SCORECARD.md](FRONTEND_SCORECARD.md) |

## License

Released under the [MIT License](LICENSE).

## Disclaimer

This project is for education and research. It is **not financial advice**, and past or backtested
performance does not predict future results. Crypto trading carries a high risk of loss, and stop-losses
are not guaranteed during gaps, outages or extreme volatility. Fees, minimum order sizes, TDS and tax
rates in the code are assumptions; confirm them with your exchange and a chartered accountant. You are
solely responsible for any money you trade.
