# Strategy research log

| Strategy family | Hypothesis | Verdict | Evidence |
|---|---|---|---|
| Trend following (EMA, slope) | Crypto has persistent multi-day trends | **Pass** | BACKTEST_REPORT.md |
| Donchian breakout | Breakouts of a 20-day range continue | **Pass** | same |
| Trend + momentum agree (ensemble) | Requiring two independent trend rules to agree removes whipsaws | **Pass, current champion** | same |
| Time-series momentum alone | Sign of 30-day return persists | Fail (too many trades, fees) | same |
| RSI mean reversion (15 min) | Short-term extremes revert | **Fail**: -97%, fees dominate | `lab.py` (perp run) |
| ML direction model (15 min, LightGBM) | Technical features predict next-4h move | **Fail**: rank-IC -0.008, -68% | MODEL_EVALUATION.md |
| Scalping / HFT / order flow | needs depth data and sub-second execution | **Rejected before testing**: no order-book feed, fee burden 0.34% round trip vs typical 15-minute move | `feasibility.py` |
| Statistical arbitrage / pairs, cross-exchange arbitrage | needs multi-venue data and transfer modelling | Not researched | - |
| News, sentiment, on-chain | unverified signal value | Not built | ARCHITECTURE.md |

Economic rationale for the survivors: crypto returns are fat-tailed and trending; a long-only trend rule with a volatility stop keeps small losses and holds winners. It loses in chop and in sharp reversals. Invalidation: sustained negative expectancy in paper/live over several months, or drawdown beyond the lab's resampled 95th percentile (about 21% for the ensemble).
