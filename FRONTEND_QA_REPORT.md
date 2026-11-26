# Frontend QA report

Date: 2026-11-25/26. Build under test: `frontend/dist` served by `python -m bot.api --port 8766` (8765 was taken by an unrelated program), real bot data, Binance live candles.

## Automated checks

| Check | Command | Result |
|---|---|---|
| TypeScript strict, 26 source + test files | `npm run typecheck` | 0 errors |
| Frontend unit tests | `npm test` | **23 passed** (3 files) |
| Production build | `npm run build` | OK; see bundle table |
| Dependency audit | `npm audit` | 0 vulnerabilities (at install) |
| API tests | `pytest tests/test_api.py` | 21 passed |
| Full Python suite | `python -m pytest -q` | **191 passed** |

Frontend tests cover: every formatter returns "—" for null/undefined/NaN/Infinity/strings and keeps a real 0; signs, units, Indian digit grouping, UTC and relative times; `DataState` loading, error + Retry, and "showing last good data"; `Table` empty state and missing-vs-zero cells; the API client rejecting unknown schema versions, turning network failures into a readable message, and sending GET only; the topbar dropping "alive" badges when a refresh fails.

API tests cover: envelope on every endpoint with no NaN; 405 on writes; 422 on bad inputs; no path traversal; security headers; no credential-like env value in any response; empty state reads as missing, not zero; mode isolation and engine-unit conversion; kill-switch utilisation; heartbeat parsing; the API never writes bot state; LightGBM shown as rejected; historical backtest labelled; readiness thresholds come from code; no protection claims live verification.

## Browser verification (built-in Chromium)

Every route was opened against real data. Programmatic audit per route (one h1, no unnamed buttons, links or inputs, no duplicate ids, no horizontal page overflow, no "NaN"/"undefined"/"[object Object]" text):

| Width | Routes | Result |
|---|---|---|
| 1920 x 1080 | all 15 + 404 | pass after fixes (one duplicate id from two chart logos, fixed) |
| 1440 x 900 | Backtesting, Events, Readiness (dark and light) | pass |
| 1366 x 768 | Command Center | pass |
| 768 x 1024 | Market Terminal | pass after fix (unlabelled topbar badges) |
| 390 x 844 | all 15 | no page overflow; drawer opens, closes on navigation |

Interactions checked: mode toggle updates URL, pressed state and data source; symbol/source toggles; theme toggle re-themes charts live and persists; sidebar collapse persists; first Tab focuses "Skip to content"; unknown route shows "Page not found"; drawer link navigates and closes the drawer.

Outage checked: with the API stopped, the topbar changed to "API offline · last data 1 min ago · LIVE DISABLED"; a page whose code had not loaded showed the page-level error with Reload while the shell kept working.

Screenshots: `docs/frontend-screenshots/` (16 files; three are marked BEFORE-fix and show the defect that was then fixed).

## Defects found and fixed during QA

| # | Defect | Fix |
|---|---|---|
| 1 | Loss-limit table clipped in the 340 px side column (Paper/Shadow) | Chart and limits now share a 2-column grid |
| 2 | Backtesting hid the out-of-sample holdout run | All current-policy runs shown, tagged in-sample / out-of-sample |
| 3 | API claimed `verified_live: true` for three protections; no live venue exists | `verified_by` text + warning callout + API test |
| 4 | Readiness domain bars used "limit used" colours (17/20 shown as warning) | `Meter progress` scale |
| 5 | Health showed 42% missing candles in green | Coverage bar on the progress scale (58% = warning) |
| 6 | Two TradingView logos produced duplicate element ids | One logo per page plus a text attribution |
| 7 | Tablet/mobile topbar showed two unlabelled "alive" badges | P / S labels and screen-reader text |
| 8 | "LIVE DISABLED" pushed off-screen at 390 px | Wordmark text hidden, badge shortened to "LIVE OFF" |
| 9 | Callout read "disabled. disabled: ..." | Text de-duplicated |
| 10 | Empty actions row added a gap under page titles | `:empty` rule |
| 11 | Topbar kept "alive" badges when the API went down | Shows "API offline" and data age; unit test |
| 12 | Control borders 1.67:1 and white-on-accent 3.68:1 (WCAG fail) | New token values, 3.3-5.0:1 |
| 13 | Hard-coded "83 trades" and "₹100" in page text | Read from the API |
| 14 | Ledger fill count showed 0 when the ledger file is missing | Shows "—" with the reason |
| 15 | `.gitignore` lacked `frontend/node_modules` and `dist`; requirements lacked FastAPI/uvicorn | Added |

## Performance (measured)

| Item | Value |
|---|---|
| Initial JS (gzip) | index 7.3 kB + vendor 112 kB + runtime 0.4 kB |
| Charts chunk (gzip, lazy) | 58.5 kB, only on Market Terminal, Paper, Shadow, Backtesting |
| Page chunks (gzip) | 0.6-2.1 kB each |
| CSS (gzip) | 5.3 kB |
| DOMContentLoaded, warm, localhost | 442 ms |
| Cumulative layout shift | 0 |
| API latency, warm | 100-270 ms per endpoint |
| `/markets` cold | about 6.3 s (Binance market load), then about 130 ms |

Not measured: FCP/LCP (the browser pane was hidden, so the page never painted for the observer), Lighthouse, a throttled-network run.

## Known gaps (open)

* No end-to-end test suite (Playwright not installed); browser checks above were manual and are not repeatable in CI.
* Accessibility was checked with automated DOM rules, token contrast maths and keyboard spot-checks, not with a screen reader or axe-core.
* Bundle: vendor chunk is 112 kB gzip (React, router, query); not split further.
* Equity chart on Paper/Shadow is built from engine log lines, so it only covers the log tail the API reads.
* The cold `/markets` call blocks for about 6 s; the UI shows a skeleton meanwhile.
* Only Chromium was tested; Firefox and Safari not tested.
