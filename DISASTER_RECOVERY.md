# Disaster recovery

**Built and tested (simulated exchange):** on every start `Engine.reconcile()` compares `state.db` with the exchange before any order: DB-only positions are closed in the ledger (PnL estimated), exchange-only positions are flattened (or adopted with a 2% stop if `adopt_orphans`), mismatched sizes adopt the exchange, missing stops are re-placed or the position flattened if the stop level is already breached. The kill-switch halt survives restarts. A failed stop placement flattens immediately.

**Not built / not tested:** database backups, restore drills, defined RTO/RPO, alert-delivery tests, behaviour during exchange outages or WebSocket gaps (REST polling only), clock-sync checks, behaviour when the whole PC is off while a live position is open (exchange-side stop is the only protection, and the live broker is untested).

**Manual runbook if live ever runs:** 1) open the exchange and confirm positions and stops by hand; 2) stop the bot; 3) fix; 4) restart so `reconcile()` runs; 5) never resume without reading its output.
