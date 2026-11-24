# Safety Rules: 24/7 India Crypto Trading Bot

## Core stack and target market
- Language: Python 3.11+ (async where applicable).
- Target exchange: Delta Exchange India (perpetual futures via REST/WebSocket API or CCXT).
  Note (verified 2026-11-24 against the public API): contracts are quoted and settled in USD
  (`BTC/USD:USD`), not INR. Whether futures avoid the 1% TDS that applies to spot must be
  confirmed with a chartered accountant before relying on it.
- Deployment: 24/7 Dockerized Linux VPS (Mumbai `ap-south-1`, UTC timezone).

## Non-negotiable safety and quantitative rules
1. **Zero look-ahead bias:** every technical indicator and ML feature MUST use `.shift(1)` so inference only sees closed candles.
2. **Exchange-side stop-loss:** every entry order MUST immediately attach an exchange-side stop-loss order. Never rely solely on local Python price checks.
3. **Crash recovery:** on startup, query the exchange API for open positions and reconcile against `state.db` (SQLite) before placing any new orders.
4. **Daily kill-switch:** halt all new entries and flatten open positions if daily drawdown reaches 3%.
5. **India tax ledger:** append every executed fill (timestamp, pair, side, qty, price, fee, realized PnL) to `trades_ledger.csv` and SQLite.
6. **Secrets:** never hardcode API keys or Telegram tokens; always read from `.env`.

## Current defaults
Rule 4 is a ceiling. The shipped default is stricter: daily 1%, plus weekly 3% and monthly 5% loss limits,
0.5% risk per trade and at most 2 positions. Spot, long-only, 1x is the default market profile; perpetual
futures are opt-in.
