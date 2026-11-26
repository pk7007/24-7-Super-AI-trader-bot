# Skills audit (rubric in SKILLS_MASTER_PROMPT.md)

Updated 2026-11-25. Evidence or zero. "N/A" points are excluded from the denominator and said so.

| Skill | Score | Status | Evidence | Open |
|---|---:|---|---|---|
| `crypto-alerts` | **8 / 9 applicable** (not yet 9/10) | built, reviewed | see below | chain point (needs the other skills); P2/P3 notes below |
| `crypto-risk` | **8 / 9 applicable** (not yet 9/10) | built, reviewed | see below | chain point. Engine sizing fixed 2026-11-25 to count costs; bot-sized orders now PASS |
| `crypto-budget` | **9 / 9 applicable** | built, reviewed | see below | first link of the chain proven (budget -> risk) |
| `crypto-exit` | 4 / 10 | baseline (author) | stop tests | no plan file, no skill |
| `crypto-signal` | 5 / 10 | baseline (author) | look-ahead safe, holdout passed | no skill, no per-pair reasons; data-fetch retry added 2026-11-25 (was the cause of 4 lost candles) |
| `crypto-timemachine` | 2 / 10 | baseline (author) | strategy-level Monte Carlo only | per-signal replay not built |
| `crypto-scanner` | 1 / 10 | baseline (author) | - | 3 hard-coded pairs |
| `crypto-ticket` | 2 / 10 | baseline (author) | paper/shadow brokers | no approval record; spot venue blocked |
| `crypto-news` | 0 / 10 | baseline (author) | - | not built |
| `crypto-report` | 3 / 10 | baseline (author) | readiness scorer | report script outside the repo |

## crypto-alerts detail
Files: `bot/alerts.py`, `bot/notify.py` (now returns delivery success), local (uncommitted) skill file `crypto-alerts`, `tests/test_alerts.py` (23 tests). Full suite: 80 passed.

| Criterion | Points | Evidence |
|---|---|---|
| Correct and tested | 2 / 2 | 23 offline tests: heartbeat, missing log/DB, step failure, no data, kill-switch, fills, levels, near stop (long and short), price failure, bad ledger row, corrupt DB, corrupt memory, delivery failure, clock skew, log-format change, CLI exit codes, 6-hour outage reminder |
| No look-ahead | N/A | makes no trading decisions |
| Safety | 2 / 2 | `test_check_never_modifies_bot_state` (hashes unchanged; SQLite opened read-only); no order code; every check fails loud (`alert_error`) instead of silent |
| Clear SKILL.md | 1 / 1 | triggers, commands, exit codes, limits. Harness registration not yet confirmed (needs a session started in the project folder) |
| Reproducible | 1 / 1 | injected clock, sender and price source; deterministic tests |
| Chains correctly | 0 / 1 | **open**: reads the real bot outputs (proven in the live drill), but the end-to-end skill chain test cannot exist until the other skills are built |
| Useful (measured) | 1 / 1 | live drill on 2026-11-24 caught 3 consecutive failed candles (23:15, 23:30, 23:45) in both bots, which the author had wrongly called a one-off |
| Independent review | 1 / 1 | `ecc:silent-failure-hunter`: first pass found 2 P0 + 4 P1 silent paths; all fixed; re-review verdict "open P0/P1: NO" |

Remaining from review (P2/P3, not blocking): a fill first seen at the moment of a memory reset is recorded, not sent (the notice now tells you to check the ledger); a deleted (not corrupt) memory file re-sends history; the watcher's last-resort alert ignores delivery failure; old keys can drop after 5,000 entries; `--json` mode omits the delivery warning.

## Found while building: data feed has no retry (affects crypto-signal and the running bots)
Both bots failed three candles in a row on 2026-11-24 with `SSLEOFError` connecting to `api.binance.com`. Single requests succeed (HTTP 200 in 0.7-1.5 s); the bot's per-candle fetch has no retry, so one dropped connection loses the whole candle. Fail-safe (no data means no trade), but no decisions are made while it lasts. **Fixed 2026-11-25** (`ResilientExchange` in `bot/data.py`); bots restarted and the 00:45 candle succeeded in both.

## crypto-risk detail
Files: `bot/riskcheck.py`, local (uncommitted) skill file `crypto-risk`, `tests/test_riskcheck.py` (44 tests).

| Criterion | Points | Evidence |
|---|---|---|
| Correct and tested | 2 / 2 | one test per block reason (risk incl. costs, leverage, stop missing/wrong side/NaN, short on spot, each kill-switch, max positions, duplicate, min order, symbol, bad inputs), exits allowed while halted, sizing mode returns a size that passes |
| No look-ahead | N/A | makes no signal decisions; uses prices you pass in |
| Safety | 2 / 2 | `test_cli_never_writes_state` (hashes unchanged, SQLite `mode=ro`); no order code; fails closed on missing/corrupt state, garbled kill-switch value, invalid position side, settings error, `--equity` above real equity |
| Clear SKILL.md | 1 / 1 | triggers, commands, exit codes, every check, limits. Harness registration not yet confirmed |
| Reproducible | 1 / 1 | pure `evaluate()`; state injected; deterministic tests |
| Chains correctly | 0 / 1 | **open**: needs crypto-budget/ticket to feed it orders |
| Useful (measured) | 1 / 1 | first real run found that the engine's own sizing breaks the 0.5% policy once costs are counted (0.532% at a 3% ATR) |
| Independent review | 1 / 1 | `ecc:silent-failure-hunter`: first pass P1s (unsized exit passed, garbled kill-switch read as clear, `--equity` raised limits, `BTC/INR` matched, settings error crashed); all fixed; re-review "open P0/P1: NO" |

Remaining P2: equity is paper cash only (positions valued at entry, conservative); a settings-error verdict has no structured check list.

## crypto-budget detail
Files: `bot/budget.py`, local (uncommitted) skill file `crypto-budget`, `tests/test_budget.py` (30 tests).

| Criterion | Points | Evidence |
|---|---|---|
| Correct and tested | 2 / 2 | same size as the engine at 1/3/6% ATR; lot-step rounding never over-risks; which limit decided (risk, 1x, free cash, slots); refusal below Rs 100 with capital needed (lot-step and 1x aware); engine-unit positions (3000 steps = 0.03 BTC) |
| No look-ahead | 2 / 2 | `--bot` uses the last CLOSED 15m candle with the engine's own freshness rule; stale candles BLOCK (test) |
| Safety | 2 / 2 | bot state unchanged (hash test); only writes `proposals/<mode>_order.json`, atomically, only on PASS; a refused `--write` removes an older proposal; every failure exits 20 |
| Clear SKILL.md | 1 / 1 | triggers, commands, limits table, reporting rules |
| Reproducible | 1 / 1 | pure `size()`; injected state; live mode isolated in one function |
| Chains correctly | 1 / 1 | every sizing runs `crypto-risk` on the exact order; the CLI exit code is the chained verdict (kill-switch and short tests) |
| Useful (measured) | 1 / 1 | live run 2026-11-25: the bot's 2-ATR stops sit 9-12% away, so a 0.5% risk budget buys $4-6 per trade, about 4-5% of the $113.60 account; this explains the low returns. Found and fixed the units bug below |
| Independent review | 1 / 1 | `ecc:silent-failure-hunter`: first pass 4 P1 (bot units read as coins in both tools, stale proposal survived a refusal, `--bot` had no freshness check, equity ignored open losses); second pass 1 P1 (early refusals kept an old proposal); all fixed with tests; final "open P0/P1: NO". 170 tests pass |

Found while building: `crypto-risk` read the engine's position size (lot-step counts) as coins, so with any position open its exposure check blocked everything and its exit check compared coins to step counts. Fixed in `riskcheck.load_context` (`coin_units`), with a test using engine-style rows. Equity is now cash plus each open position at its stop (conservative).
