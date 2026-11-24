# Model evaluation

**Candidate:** LightGBM 3-class (down/flat/up) on 17 shifted technical features, pooled over BTC/ETH/SOL, retrained every 14 days on a rolling 90-day window with labels purged at the boundary (`backtest.walk_forward_probs`).

**Results (clean Binance data, 444 out-of-sample days):**
* Spearman rank correlation of P(up) with the forward 4-hour return: **-0.008** (no skill).
* Strategy return **-68%**, profit factor 0.50, fees $441 on a $1,000 account (BTC itself fell 44%).
* Independent freqtrade/FreqAI LightGBM run on Binance data, Aug-Nov 2026: **-15.7%**, profit factor 0.46. Two independent engines agree.

**Decision:** rejected. Kept in the repo as `STRATEGY=ml` only, never default, never promoted. Complex model did not beat a no-model baseline (cash) after costs.

**Not done:** probability calibration, uncertainty estimates, SHAP/explainability, MLflow versioning, champion-challenger framework, drift monitoring, deep learning, reinforcement learning. No evidence yet justifies building them for this horizon; a first honest step would be daily-horizon features with purged cross-validation.

**Data-integrity note:** an earlier run on Delta India candles (-24%) was invalid because that feed contained impossible prices (see AUDIT.md).
