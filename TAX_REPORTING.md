# Tax reporting

**Exists:** every fill is recorded in `trades_ledger.csv` and SQLite with timestamp, pair, side, qty, price, fee, realized PnL, reason, order id (RULE 5). `python -m bot.main report --mode paper|live` prints estimated tax (30% of positive round trips, no loss set-off) and the backtest metrics include estimated TDS (1% of sale value).

**Limitations:**
* INR values use one fixed `USDT_INR` rate, not the rate on each trade date.
* No FIFO/lot accounting, no per-financial-year report, no CSV export for filing.
* Realized PnL for live fills is computed from the stored entry price (gross), not matched to exchange statements.
* The 30% / 1% rules are unverified (see COMPLIANCE.md). Distinguish economic PnL from taxable gain; a CA must sign off.

**To do (P2):** historical INR rates, FY-wise export, reconciliation against exchange statements.
