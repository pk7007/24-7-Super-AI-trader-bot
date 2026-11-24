# Risk management (implemented vs. required by the master prompt)

| Control | Prompt default | Implemented | Where |
|---|---|---|---|
| Risk per trade | 0.25-0.5% | 1.0% in trend profile (**above** prompt range); feasibility report uses 0.5% | `config.py` |
| Leverage | disabled | spot profile = 1.0x; perps opt-in (`MARKET=perp`) | `config.py` |
| Short selling | disabled | blocked on spot; entries only | `strategy.decide` |
| Daily loss limit | ~1% | **3%** kill-switch: flatten + halt until next UTC day, survives restart | `risk.DailyKillSwitch` |
| Weekly / monthly loss limit | 3% / - | **not implemented** | - |
| Max open positions | yes | 3 | `engine` |
| Exchange-side stop on entry | - | yes; flatten if placement fails | `engine._enter` |
| Min order / economic viability | refuse | yes (`min_order_inr`, assumed Rs 100) | `engine` |
| Venue price mismatch guard | - | yes, 0.5%, fail-safe | `engine._venue_ok` |
| Stale-data guard | no stale trades | yes (stale candle -> skip cycle) | `engine._signal` |
| Max exposure per asset / exchange, correlation cap | yes | **not implemented** | - |
| VaR / Expected Shortfall | yes | **not implemented** (Monte Carlo drawdown in lab only) | `lab.monte_carlo` |
| Strategy suspension on drawdown | 5-8% | **not implemented** | - |
| Manual kill switch | yes | only by stopping the process / `flatten_all` (no UI) | `engine` |

Stops are not guaranteed: gaps, slippage and exchange outages can exceed the modelled loss. Backtests model stop slippage but not outages.
