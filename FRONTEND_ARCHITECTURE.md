# Frontend architecture

## Shape

```
bot processes (paper, shadow)          read-only API (python -m bot.api)          browser
  write state/*, reports/*   ──read──▶  FastAPI, 127.0.0.1 only, GET only  ──JSON──▶  React SPA (frontend/dist)
                                        also serves frontend/dist (one origin)
```

* The API never writes. SQLite is opened with `mode=ro`; files are only read. A test hashes the bots' state files before and after calling every endpoint.
* The API and the UI run apart from the bots. Stopping or crashing either one has no effect on trading.
* One origin: `npm run build` writes `frontend/dist/`, which the API serves. No CORS is needed in production; in development Vite proxies `/api`.

## Stack (versions pinned in `frontend/package.json`)

| Layer | Choice | Why |
|---|---|---|
| UI | React 19 + TypeScript (strict) | Typed contracts, mature ecosystem. |
| Build | Vite 8 | Fast builds, code splitting by route. |
| Routing | react-router-dom 7 (`createBrowserRouter`) | Lazy routes, error elements. |
| Data | TanStack Query 5 | Caching, polling, retry, stale/error states in one place. |
| Charts | TradingView lightweight-charts 5 (Apache-2.0) | Purpose-built for financial time series; 58 kB gzip, loaded only on chart pages. |
| Icons | lucide-react | Tree-shaken SVG icons. |
| Fonts | Inter, IBM Plex Mono via @fontsource (OFL) | Self-hosted: no third-party font requests (CSP `font-src 'self'`). |
| Tests | Vitest + Testing Library + jsdom | Same toolchain as Vite. |

**No Tailwind.** The design system is a small set of CSS custom properties (`src/styles/tokens.css`) and one component stylesheet (`src/styles/app.css`, about 900 lines). Reasons: themes switch by changing one attribute; every value is a named token checked for contrast; no build plugin or class soup; the whole style layer is 5 kB gzip.

**No Playwright.** It is not installed on this machine and the PC is resource-constrained. Browser verification used a built-in Chromium browser pane driven during development: every route at 1920, 1440, 1366, 768 and 390 px, light and dark, keyboard focus, the mobile drawer, and an API outage. See FRONTEND_QA_REPORT.md. Adding Playwright later is the main open test gap.

## Source layout

```
frontend/
  index.html              dark theme by default, inline SVG favicon
  vite.config.ts          proxy /api (ATL_API overrides the target), vendor/charts chunks
  src/
    main.tsx              fonts, QueryClient (retry 1, no background polling), theme, router
    app/                  App.tsx (routes, page error boundary), Shell.tsx (topbar, sidebar), nav.ts, theme.ts
    components/ui/        Panel, Metric, Strip, Badge, Status, Callout, DataState, Table, KV, Meter, Seg, ModeBanner ...
    components/charts/    CandleChart, LineChart (lightweight-charts, colours from tokens)
    pages/                one file per route + shared.tsx, tables.tsx
    services/api.ts       typed fetch of the envelope, one hook per endpoint with its poll interval
    types/api.ts          response shapes; null always means "not available"
    utils/format.ts       formatters; missing input always returns "—"
    styles/               tokens.css, app.css
  tests/                  format, components, topbar outage (23 tests)
```

## Routes

| Path | Page | Main endpoints |
|---|---|---|
| `/` | Command Center | overview, markets, health |
| `/market` | Market Terminal (`?symbol=`, `?source=live\|cached`) | candles, markets, risk, fills, signals |
| `/paper`, `/shadow` | Mode workspaces | overview, positions, fills, signals, intents |
| `/orders` | Orders & Positions (`?mode=`) | positions, fills, intents |
| `/signals` | Signals (`?mode=`) | signals |
| `/strategies` | Strategy Lab (incl. Monte Carlo, LightGBM rejected) | strategies |
| `/backtests` | Backtesting (current-policy, holdout, historical curve labelled) | backtests |
| `/feasibility` | Capital Feasibility | feasibility |
| `/risk` | Risk Management | risk |
| `/readiness` | Live Readiness | readiness |
| `/ledger` | Ledger & Tax (`?mode=`) | ledger |
| `/health` | System Health | health |
| `/events` | Event Log (`?mode=`, level filter, search) | events |
| `/settings` | Settings (theme only) | none |

Mode and symbol live in the URL, so views can be linked and survive reloads.

## Data behaviour

* **Polling** matches how often data really changes (the engine writes once per 15-minute candle): overview, positions, health 30 s; markets, live candles, fills, signals, ledger, events 60 s; readiness 5 min; lab reports, backtests, feasibility once. Hidden tabs stop polling.
* **Missing is not zero.** The API returns `null` for anything unknown; `format.ts` renders it as "—" with an accessible "not available" label. Unit-tested.
* **Errors.** No data yet + error: an error state with Retry. Data + failed refresh: the last data stays with a "Showing last good data" warning. The topbar switches to "API offline · last data N min ago" and drops the heartbeat badges, so a dead API can never look healthy (unit-tested and checked in the browser).
* **Page isolation.** Each route is wrapped in an error boundary; a failing page (including a chunk that cannot load while the API is down) shows a message and a Reload button, and the shell keeps working.

## Security

* API bound to 127.0.0.1; no authentication, so it must not be exposed. GET/HEAD/OPTIONS only (others: 405).
* Query parameters are enums or bounded integers (bad values: 422). The static route resolves paths and refuses anything outside `frontend/dist`.
* Headers: `X-Content-Type-Options: nosniff`, `Referrer-Policy: no-referrer`, `X-Frame-Options: DENY`; API responses `Cache-Control: no-store`; the page gets a strict CSP (`default-src 'self'`, no inline script, `frame-ancestors 'none'`).
* Errors return the exception class name only: no paths, environment or tracebacks. A test checks that no credential-like environment value appears in any response.
* The UI has no order entry, no buttons that change bot state, and no settings that reach the bots.

## Running it

```
pip install -r requirements.txt
cd frontend && npm ci && npm run build && cd ..
python -m bot.api                 # http://127.0.0.1:8765 ; use --port 8766 if 8765 is taken
```

Development: `python -m bot.api` in one shell, `npm run dev` in `frontend/` (http://127.0.0.1:5173). If the API runs on another port: `ATL_API=http://127.0.0.1:8766 npm run dev`.
