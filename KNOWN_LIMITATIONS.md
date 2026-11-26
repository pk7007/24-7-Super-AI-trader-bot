# Known limitations (read before trusting any number)

1. **No live-money evidence.** All results are backtests, a 45-day replay and a few hours of paper trading.
2. **Selection bias.** Candidates were compared on the same 3.6-year window; the winner's return is optimistic.
3. **Crash test is one sample.** A pre-registered 2021-2022 holdout (includes the 2022 crash) passed: +5.3%, DD -5.5%, 40 trades, while BTC fell 61%. One period, small sample, low return.
4. **Spot execution does not exist.** No spot connector is built. CoinDCX spot (researched) has no documented exchange-side stop, no sandbox and no documented no-withdrawal key scope; its official fee page could not be read (HTTP 403). See EXCHANGE_RESEARCH.md.
5. **`DeltaBroker` (perpetuals) was never run against the real API** - testnet check blocked on a demo-site key.
6. **Signals come from Binance, execution would be elsewhere** (basis risk). Delta India's own candle history failed validation.
7. **Fees, minimum order size, TDS and tax rates are assumptions** (`config.py`, `feasibility.py`) - not verified against official sources this session.
8. **Paper broker is optimistic:** no spread/depth model, fixed slippage, 1-minute stop checks, no funding or liquidation.
9. **One regime-sensitive style.** Trend following loses in chop; it had ~30% win rate and long flat periods.
10. **No news, sentiment, on-chain or order-book intelligence; no regime or drift agent; no dashboard; no HTTP API.**
11. **Risk limits differ from the prompt's suggestions:** daily kill-switch is 3% (prompt: ~1%); weekly 6% / monthly 10% limits added but their values are my assumptions; no VaR/ES; no correlation cap.
12. **Operational:** runs on one PC as scheduled tasks (only while logged in and awake). A 24/7 server package is prepared (DEPLOYMENT.md) but not deployed, and the Docker image has never been built. External heartbeat configured (2026-11-27; both bots share one check) and a daily backup task with a restore drill; backups stay on the same disk until copied off.
13. **No CI yet.** The code is on GitHub, but tests only run locally; there is no automated test workflow.
