# Agent routing and rules (read by coding-agent sessions, e.g. Codex, in this repo)

**Two kinds of "agent" exist here; do not confuse them.**
1. **Development-session subagents** (LLM). They run only inside a coding session, on demand, and stop when the session ends. Definitions: local agent definition files (kept out of the repo) plus installed agent plugins. The names in the routing table describe the review role; use whatever equivalent reviewer your tool provides.
2. **Runtime workers** (deterministic Python, no LLM). Paper bot, shadow bot, readiness scorer. These are what run "continuously". No LLM is ever in the order path.

## Hard rules for every agent
- Never read, print or forward `.env` or any credential. Research agents never get exchange keys.
- No agent may enable live trading, raise capital, enable leverage/derivatives, change critical risk limits, deploy an unvalidated model, add paid services, or grant exchange permissions. Those need the human's explicit approval in chat.
- No agent approves its own critical change: risk, strategy and readiness changes need the matching independent agent below, and the author is never the reviewer.
- Backtest numbers are never called profit. Missing evidence scores zero.

## Routing (task -> agents, in order). Use the lightest set that covers the task.
| Task | Agents |
|---|---|
| Risk config / engine / sizing / kill-switch change | implement -> `ecc:tdd-guide` (tests first) -> **`risk-auditor`** -> `readiness-verifier` |
| Strategy, parameter, lab or backtest claim | implement -> **`quant-validator`** -> `risk-auditor` if defaults change |
| ML model change | `ecc:mle-reviewer` -> `quant-validator` |
| Exchange / broker adapter change | implement -> `ecc:security-reviewer` -> `ecc:silent-failure-hunter` -> `risk-auditor` |
| Bug fix | `superpowers:systematic-debugging` workflow -> regression test -> `ecc:python-reviewer` |
| New dependency | `ecc:security-reviewer` (supply chain) |
| Tax / compliance / exchange eligibility | **`india-compliance-researcher`** (sourced findings) -> human / CA |
| Any readiness score, audit score or "done" | **`readiness-verifier`** last |
| Codebase search (wide) | `Explore` |
| Simple doc edit, one-line fix | no subagent |

## Budgets and limits (development sessions)
- At most 2 subagents in parallel per task; no subagent spawns another; one retry, then report the failure.
- Strongest available model for independent risk/quant validation; a lighter model for research and verification; deterministic code for all maths, sizing, risk enforcement and accounting.
- Reuse existing reports (`reports/*.json`, `BACKTEST_REPORT.md`, `CHANGELOG.md`) before re-running anything.

## Project memory (no secrets)
`CHANGELOG.md` (what changed and why), `KNOWN_LIMITATIONS.md`, `BACKTEST_REPORT.md`, `HOLDOUT_PROTOCOL.md`, `reports/*.json`, `LIVE_TRADING_READINESS.md` / `reports/readiness.json` (`reports/` and `AGENT_REGISTRY.json` exist only on the bot's PC, not in the repo). Read the relevant ones before repeating work. `AUDIT_REPORT.md` is the current audit; `DEPLOYMENT.md` describes how the bots run.

## Runtime workers
As of 2026-11-28 paper and shadow run on the user's Windows PC from the scheduled tasks `IndiaCryptoBot-paper` / `IndiaCryptoBot-shadow` (at logon and every 10 minutes; they restart a dead bot and exit if it is already running). `IndiaCryptoBot-backup` runs `bot.backup --drill` daily at 09:00 local. To restart a bot: stop its `python -m bot.main <mode>` processes (the venv launcher and its child), then `schtasks /run /tn IndiaCryptoBot-<mode>`; say why before stopping or starting one. The outside heartbeat (`HEARTBEAT_URL` in `.env`) pings every 5 minutes. Both bots are flat (no positions). Planned home: the 24/7 server in DEPLOYMENT.md (not yet created). Never start a second copy by hand; never add a live task. Changing these tasks needs the human's go-ahead. Recent incident and fixes: top of `CHANGELOG.md`.
