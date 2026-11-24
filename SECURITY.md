# Security status

## Implemented and tested
* Secrets only from environment / `.env` (gitignored); a test scans `bot/` for hard-coded key patterns.
* Live trading needs `BOT_MODE=live` **and** `I_UNDERSTAND_LIVE_RISK=yes`; `DeltaBroker` refuses without keys; `testnet-check` refuses non-testnet.
* Paper and live state/ledgers are isolated by directory, so they cannot be confused.
* Exchange-side stop on every entry; flatten if it cannot be placed; unknown exchange positions are flattened at startup.
* No LLM or external text reaches order placement (none exists in the pipeline).

## Not implemented
MFA, RBAC, HTTPS/web auth (there is no web UI), encrypted backups, secret rotation tooling, dependency vulnerability scan (`pip-audit` not run), audit-log tamper protection, IP allow-list enforcement (exchange-side only).

## Incidents during development (rotate these)
* A production Delta API key/secret appeared in the chat transcript and a second production key was stored in `.env`. Treat both as compromised: delete them on the exchange. Use trade-only, no-withdrawal keys, IP-whitelisted.
* `.env.example` once contained real values; it has been cleaned. It is not gitignored, so never put secrets there.

## Rules
Never enable withdrawal permission. Never commit `.env`. Use testnet keys for testing.
