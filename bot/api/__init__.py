"""Read-only observational HTTP API for the AI Trade Labs frontend.

It reads what the bots already write (state.db read-only, paper_exchange.json, ledgers, logs, reports) and
never starts a bot, places an order, changes a setting, or returns environment values. See
FRONTEND_API_CONTRACT.md.
"""
