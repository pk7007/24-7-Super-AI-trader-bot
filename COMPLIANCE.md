# Compliance (India) - STATUS: NOT VERIFIED

No authoritative source was consulted in this session, so **nothing below is verified for 2026**. These are items to confirm with the Income Tax Department / a chartered accountant / the exchange's own terms before real money:

* Tax on virtual digital assets (the code assumes a flat 30% on gains, no loss set-off, from Sec 115BBH).
* TDS on transfers (the code assumes 1% of sale value, Sec 194S) and any thresholds.
* Whether crypto **derivatives** (Delta perpetuals) are taxed or withheld the same way - unknown.
* Exchange eligibility, KYC and FIU-IND registration of any exchange you use. Binance is used here only as a public price feed; trading on it is not assumed to be permitted.
* Rules on leverage, margin, and shorting for Indian residents.
* Cross-border and foreign-exchange rules if funding a non-Indian venue.

**Partly checked on 2026-11-24 (see [EXCHANGE_RESEARCH.md](EXCHANGE_RESEARCH.md)):** official Income Tax Department material confirms 1% TDS under Sec 194S on transfer of a VDA (thresholds are inconsistent across sources; 20% without PAN is reported). The 30% Sec 115BBH rate is from secondary sources. FIU-IND reportedly publishes no current list of registered exchanges; it issued notices to 25 offshore platforms in Oct 2025. Still verify the current statute/Finance Act text and the exchange's own registration.

The compliance configuration is `bot/config.py` (`usdt_inr`, fee fields) and `bot/feasibility.py` (`Assumptions`). They are constants, not a versioned legal database. Treat all tax figures the bot prints as estimates.
