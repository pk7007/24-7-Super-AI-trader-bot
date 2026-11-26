# Frontend scorecard

**These scores rate the interface only. They say nothing about trading readiness**, which is 43/100 (DEVELOPMENT ONLY, scored by `bot/readiness.py`). A good-looking dashboard does not make the bot ready for real money.

Scored against the evidence in FRONTEND_QA_REPORT.md. A score of 9 or 10 needs repeatable evidence; where the evidence is a one-off manual check, the score stays below 9.

| Area | Score /10 | Evidence | What would raise it |
|---|---:|---|---|
| Data truthfulness (no fabrication, missing ≠ zero, labels) | 9 | Every figure traces to a bot file or report; formatter + API tests for missing vs zero; simulated, cached and historical labels; LightGBM rejected; overstated protection claim found and removed (tested) | Contract tests that diff UI fields against API schema automatically |
| Safety (read-only, no execution paths, localhost) | 9 | GET-only (405 tested), no write test, no order/kill-switch controls, 127.0.0.1 bind, CSP, secrets test | Authentication if it is ever exposed beyond localhost |
| Information design / usefulness | 8 | Surfaced real problems (missed candles, step failures, stale readiness, policy discrepancy, holdout) on first screens | Alerts history and trade-level drill-down once trades exist |
| Visual design and consistency | 8 | Token system, both themes, consistent components; screenshots at 5 widths | Design review by a second person; icon and density polish |
| Responsiveness | 8 | No overflow on any route at 390 px; drawer; tables scroll in place | Mobile-first table layouts (cards) instead of horizontal scroll |
| Accessibility | 7 | Contrast measured for every token pair (two failures fixed); landmarks, skip link, one h1, labelled controls, meters, reduced motion | Screen-reader pass (NVDA), axe-core in CI, chart text alternatives beyond a label |
| Resilience / error states | 8 | Loading, error + Retry, last-good-data warning, topbar outage (unit + browser), page error boundary | Automated outage tests in a browser |
| Performance | 7 | 120 kB gzip initial JS, lazy charts, 442 ms DCL locally, CLS 0 | Lighthouse run, FCP/LCP measurement, smaller vendor chunk, faster cold `/markets` |
| Code quality and types | 8 | Strict TS, 0 errors, typed hooks per endpoint, small shared primitives | Generate types from the OpenAPI schema; lint config |
| Test coverage | 6 | 23 frontend unit tests + 21 API tests | Page-level tests and a Playwright E2E suite |
| Documentation | 8 | Six frontend reports, README section, API docs at `/api/docs` | Short operator guide with screenshots |

**Overall: 7.8 / 10.** Usable and honest, not yet "institutional-grade" by the prompt's own bar: that needs the E2E suite, a screen-reader pass and measured paint metrics. No area is scored 10, and the two 9s rest on automated tests.
