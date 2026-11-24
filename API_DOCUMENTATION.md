# API documentation

There is **no HTTP API** (FastAPI was evaluated, not built). The interface is the CLI:

| Command | What it does |
|---|---|
| `fetch [--days N] [--refresh]` | Download Binance candles (validated) into `data/` |
| `backtest` | Walk-forward / rule backtest with costs; writes `reports/backtest_*` |
| `lab [--only a,b] [--taker x] [--tag t]` | Compare strategy candidates; Monte Carlo; promotion gate |
| `feasibility` | Capital feasibility table -> `reports/feasibility.md` |
| `train` | Fit the (rejected) LightGBM model |
| `replay [--days N]` | Run the full engine over history on the paper exchange |
| `paper` | 24/7 paper trading on live prices |
| `live` | Real orders (needs consent flags + keys; broker untested) |
| `testnet-check` | Testnet-only broker verification checklist |
| `report [--mode m]` | Summarise a ledger |

Settings: `.env` (see `.env.example`): `BOT_MODE`, `MARKET` (`spot` default | `perp`), `STRATEGY` (`trend` default | `ensemble` | `ml`), `START_EQUITY_USD`, `USDT_INR`, `DELTA_*`, `TELEGRAM_*`.
