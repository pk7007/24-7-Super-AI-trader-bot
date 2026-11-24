# Spot exchange research (2026-11-24)

**Method and limits.** Web search plus a read of the official CoinDCX API docs (`docs.coindcx.com`). CoinDCX's fee pages returned **HTTP 403** to automated fetches, so fee numbers below are from third-party summaries. Parts of the API page were read through a summary and are marked [S]. Only CoinDCX was researched in depth; CoinSwitch, Mudrex and others were **not** evaluated. Nothing here is legal advice.

## Findings

| Question | Finding | Source / status |
|---|---|---|
| Is a venue legally usable by an Indian resident? | CoinDCX, WazirX and CoinSwitch were named among 28 FIU-IND-registered providers in Dec 2023; a later parliamentary reply reportedly counts 54 registered by 9 Mar 2026. FIU-IND reportedly publishes **no current list**. In Oct 2025 FIU-IND issued notices to **25 offshore platforms** for operating without PMLA compliance. | Secondary (news, PIB, Lok Sabha); **verify directly with FIU-IND and the exchange**. Implication: Binance etc. stay **price feeds only**. |
| Authentication | API key + HMAC-SHA256 signature over a JSON body; headers `X-AUTH-APIKEY`, `X-AUTH-SIGNATURE`; docs inconsistent on timestamp unit (seconds vs milliseconds). | Official docs |
| Key permission scopes | Only an optional "bind IP address" checkbox is documented. **Trade-only / no-withdrawal scope: not stated.** | Official docs - **blocks SECURITY rule 7 until checked in the dashboard** |
| Sandbox / testnet | **Not stated** - no safe place to test orders. | Official docs |
| Spot order types | Create-order enum: `market_order`, `limit_order`. `markets_details` also lists `stop_limit` and `take_profit_limit`, and order objects carry `stop_price`, but **no spot request parameter for a stop price is documented**. | Official docs - **conflicts with RULE 2 (exchange-side stop)** |
| Order sizing | `GET /exchange/v1/markets_details` returns `min_quantity`, `min_notional`, `step`, precision, `max_quantity`, `order_types` per market. Read at runtime; do not hard-code. | Official docs |
| Limits | Per 60 s: create order 2000, cancel 2000, status 2000, active orders 300, cancel-all 30; max 25 open orders per market. | Official docs |
| Data | REST candles (1m, 15m, 1h, 1d; max 1000), orderbook, trades; WebSocket `wss://stream-spot.coindcx.com` (candles, trades, depth) and private order/balance updates. | Official docs |
| Fees | Third-party: INR pairs about **0.50%** maker and taker at the entry tier; crypto-to-crypto (e.g. USDT) about **0.17%**; GST 18% on fees stated for futures, assume it applies. | **Unverified** (official page blocked) |
| TDS | Official Income Tax Department material: **1% under Sec 194S** on payment for transfer of a VDA; sources disagree on thresholds (Rs 10,000 / Rs 50,000) and 20% without PAN. 30% flat tax (Sec 115BBH), cost of acquisition only. No source showed a change for 2026. | Official site (search snippets) + secondary - **confirm current text** |

## What this does to the backtests
Re-run at **0.50% taker** (round trip about 1.28% with GST and slippage), spot long-only, 3.6 years: **ensemble +78% / -17% DD / PF 2.14 (passes)**, Donchian +61% (passes), EMA trend +14% (**fails**, 31% resampled chance of loss). Fees are survivable by the ensemble; they are not the blocker.

## Blockers and options
1. **No documented spot stop order -> RULE 2 cannot be met on CoinDCX spot as documented.** Options: (a) ask CoinDCX support / test in the dashboard whether `stop_limit` accepts a stop price; (b) accept a *software* stop plus kill-switch (explicitly violates RULE 2 - your decision, not mine); (c) evaluate other venues (CoinSwitch Pro API, Mudrex) - **not researched**.
2. **No sandbox** -> first live order would be real money; needs a different test plan (minimum-size manual pilot).
3. **Key permissions unverified** -> cannot guarantee no-withdrawal.
4. **Fees and minimums unverified** from an official page -> read `markets_details` and the dashboard fee page by hand.

## Recommendation
Keep paper trading on the spot ensemble. Do not write a live spot connector until (1) a stop-order path is confirmed on the chosen venue and (2) key scoping is verified. Sources: docs.coindcx.com; incometaxindia.gov.in (194S); PIB release on FIU registrations; news reports on FIU notices to offshore platforms.
