# Frontend API contract (schema 1.0)

Server: `python -m bot.api [--port 8765]`, bound to 127.0.0.1. Implementation: `bot/api/app.py`, readers in `bot/api/sources.py`.
Interactive schema: `/api/docs` (OpenAPI at `/api/openapi.json`). Tests: `tests/test_api.py` (21 tests).

## Rules that hold for every endpoint

* **GET only.** POST, PUT, PATCH and DELETE return `405 {"detail": "read-only API: only GET is allowed"}`.
* **Envelope.** Every response is `{"schema_version": "1.0", "observed_utc": "<ISO-8601 UTC>", "data": ...}`. The client rejects any other schema version.
* **Missing is `null`, never `0`.** Each reader also returns an `availability` string ("ok", or "missing (why)").
* **No NaN or Infinity** in any response (non-finite floats become `null`).
* **Inputs are whitelisted**: `mode` ∈ {paper, shadow}, `symbol` ∈ {BTC, ETH, SOL}, `source` ∈ {live, cached}, limits bounded. Anything else: `422`.
* **Errors** return `500 {"detail": "internal error (<ExceptionClass>)"}`: no paths, environment or traceback.
* **Headers**: API responses `Cache-Control: no-store`, `X-Content-Type-Options: nosniff`, `Referrer-Policy: no-referrer`, `X-Frame-Options: DENY`.
* **Simulation flag.** Mode data carries `simulated: true`; nothing in this API reflects a real exchange account.

## Endpoints (`/api/v1/...`)

| Endpoint | Params | `data` (main fields) | Source |
|---|---|---|---|
| `overview` | none | `modes.{paper,shadow}`: `heartbeat`, `equity{value,currency,basis,availability}`, `realized_pnl`, `fill_count`, `open_positions`, `open_risk_usd`, `kill_switches.{daily,weekly,monthly}`, `entries_halted`; `readiness{score,classification,deployment_state,live_trading_allowed,blockers}`; `live_trading` | state files, logs, readiness |
| `markets` | none | `rows[]`: `symbol`, `signal_pair`, `execution_instrument`, `execution_venue`, `last_close`, `last_closed_utc`, `data_age_min`, `change_24h_pct`, `paper_decision`, `shadow_decision`, `source` | Binance public data (30 s cache) |
| `candles` | `symbol=BTC`, `limit=300` (20-1000), `source=live` | `bars[]{t,o,h,l,c,v,closed}`, `last_closed_utc`, `data_age_min`, `source`, `signal_pair`, `execution_instrument`, `timeframe` | Binance live or `data/*_binance.csv` |
| `positions` | `mode=paper` | `rows[]`: DB columns + `coins`, `notional_usd`, `risk_to_stop_usd`, `side_label`; `note` | `state.db` (read-only) |
| `fills` | `mode=paper` | `rows[]` (newest first, max 1000), `simulated` | `state.db` |
| `signals` | `mode=paper`, `limit=200` (1-2000) | `rows[]{logged_utc,candle_label_utc,equity,held,decisions{BTC,ETH,SOL},no_data}` newest first | engine log lines |
| `intents` | none | `rows[]` as written by the shadow broker | `shadow_intents.csv` |
| `risk` | none | `effective{...}`, `policy_ceiling{...}`, `discrepancies[]`, `round_trip_cost_pct`, `protections[]{name,status,verified_by}`, `modes.{paper,shadow}` kill switches | `bot/config.py`, `state.db` |
| `strategies` | none | `rows[]{id,label,status,evidence_tag,evidence_policy,metrics,monte_carlo,subperiod_returns_pct,rejected_because}` | lab reports, MODEL_EVALUATION.md |
| `backtests` | none | `lab_reports[]{tag,window,market,taker_fee,classification,candidates,generated_utc}`, `historical_equity{points,drawdown,metrics,classification}` | `reports/*.json` |
| `readiness` | none | `report` (readiness.json), `thresholds`, `weights`, `states`, `anytime_states`, `live_states`, `current_state`, `note` | readiness.json + `bot/readiness.py` |
| `feasibility` | none | `rows[]` per capital level, `assumptions`, `fees`, `usdt_inr`, `data` | `bot/feasibility.py` (cached daily) |
| `ledger` | `mode=paper` | `rows[]` (CSV columns), `availability`, `simulated`, `note` | `trades_ledger.csv` |
| `health` | none | `modes.{paper,shadow}`: `heartbeat`, `log`, `database`, `ledger`, `candles_last_24h`, `expected_candles_24h`, `step_failures_24h`, `feed_retries_24h`, `warnings_24h`, `restarts[]`, `lock_file_present`; `not_collected[]` | logs, state files |
| `events` | `mode=paper`, `limit=200` (1-1000) | `rows[]{ts_utc,level,logger,message}` newest first | `state/<mode>.log` |

### Semantics worth knowing

* **Heartbeat**: `alive` if the last engine candle line is younger than 40 minutes, `stale` if older, `unknown` if there is none. Same threshold as the Docker health check.
* **Log times** are written in the PC's local time and converted to UTC by the API.
* **Engine units**: `positions.contracts` is the engine's lot unit; `coins = contracts x lot step` (BTC 0.00001, ETH 0.0001, SOL 0.01 on spot).
* **Equity** is paper cash with open positions valued at entry; `basis` says so.
* **Classification of lab reports**: "current policy" only when the report records the current 0.5% / 2-position settings; otherwise "historical ...". The historical equity curve is always labelled "NOT the current policy".
* **verified_by** never claims verification on a real exchange: none is connected (tested).

## Frontend side

`frontend/src/services/api.ts` holds one typed hook per endpoint and its poll interval; `frontend/src/types/api.ts` holds the shapes. When the API changes a field, change both and the page that reads it; `npm run typecheck` catches the rest.
