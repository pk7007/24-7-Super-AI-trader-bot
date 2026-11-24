# Cost analysis

* **Software/data:** Rs 0. Binance public candles, Delta public tickers, open-source libraries. No LLM or paid API is used; the pipeline has no per-tick AI calls.
* **Hosting:** Rs 0 on your own PC (electricity, uptime risk) or a free-tier VM; a small VPS is a few hundred rupees a month (**price unverified**).
* **Trading costs (assumed, verify):** spot taker 0.10% x 1.18 GST + 0.05% slippage per side = about 0.34% round trip; plus 1% TDS withheld on each sale (a cash-flow drag, not a cost).
* **Capital level:** see `reports/feasibility.md`. At Rs 1,000 the risk budget (0.5% = Rs 5) cannot reach a Rs 100 minimum order, so the system refuses; from Rs 2,500 it is feasible on paper.
* **Net benefit:** unproven until paper/live results exceed these costs over months.
