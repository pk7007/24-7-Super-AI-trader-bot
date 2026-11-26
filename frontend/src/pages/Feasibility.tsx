import { useFeasibility } from "../services/api";
import { Badge, Callout, DataState, KV, PageHead, Panel, Source, Table, Val } from "../components/ui";
import type { Row } from "../types/api";
import { frac, inr, num, pct } from "../utils/format";

export default function Feasibility() {
  const q = useFeasibility();
  return (
    <div className="page stack">
      <PageHead
        crumbs="Research"
        title="Capital Feasibility"
        lede="Whether a given account size can trade the strategy at all once the 0.5% risk budget, the exchange minimum order, fees, GST and 1% TDS are applied."
      />
      <DataState q={q} rows={6}>
        {(d) => {
          const a = (d.assumptions ?? {}) as Record<string, number>;
          const fees = (d.fees ?? {}) as Record<string, number>;
          return (
            <>
              <Callout tone="info" title="Estimates.">
                Based on BTC's recent daily ATR ({String(d.data ?? "cached data")}). Tax and TDS figures are estimates for planning, not filing advice; confirm with a chartered accountant.
              </Callout>
              <div className="grid cols-main-side">
                <Panel title="By account size" flush>
                  <Table<Row>
                    caption="Capital feasibility by account size"
                    rows={d.rows}
                    cols={[
                      { key: "capital_inr", label: "Capital", num: true, render: (r) => <strong><Val v={inr(r.capital_inr)} /></strong> },
                      { key: "risk_budget_inr", label: "Risk / trade", num: true, render: (r) => <Val v={inr(r.risk_budget_inr)} /> },
                      { key: "position_notional_inr", label: "Position size", num: true, render: (r) => <Val v={inr(r.position_notional_inr)} /> },
                      { key: "meets_min_order", label: `Meets ${inr(a.min_order_inr)} min`, render: (r) => (r.meets_min_order ? <Badge tone="ok">yes</Badge> : <Badge tone="bad">no</Badge>) },
                      { key: "round_trip_cost_inr", label: "Round-trip cost", num: true, render: (r) => <Val v={`₹${num(r.round_trip_cost_inr)}`} /> },
                      { key: "tds_withheld_per_sale_inr", label: "TDS per sale", num: true, render: (r) => <Val v={`₹${num(r.tds_withheld_per_sale_inr)}`} /> },
                      { key: "break_even_move_pct", label: "Break-even move", num: true, render: (r) => <Val v={pct(r.break_even_move_pct, 3, false)} /> },
                      { key: "verdict", label: "Verdict", wrap: true, render: (r) => <Badge tone={String(r.verdict).startsWith("REFUSE") ? "bad" : String(r.verdict).startsWith("OK") ? "ok" : "warn"}>{String(r.verdict)}</Badge> },
                    ]}
                  />
                </Panel>
                <Panel title="Assumptions">
                  <KV
                    items={[
                      ["Risk per trade", <Val v={frac(a.risk_per_trade)} />],
                      ["Stop distance", <span>{a.stop_atr ?? "—"} × daily ATR</span>],
                      ["Minimum order", <Val v={inr(a.min_order_inr)} />],
                      ["Taker fee", <Val v={frac(fees.taker, 2)} />],
                      ["GST on fees", <Val v={fees.gst ? `${((fees.gst - 1) * 100).toFixed(0)}%` : "—"} />],
                      ["Slippage", <Val v={frac(fees.slippage, 2)} />],
                      ["TDS on sale", <Val v={frac(a.tds_rate, 0)} />],
                      ["Tax on gains", <Val v={frac(a.tax_rate, 0)} />],
                      ["USDT/INR", <Val v={num(d.usdt_inr as number)} />],
                    ]}
                  />
                  <div className="section-gap">
                    <Source>bot/feasibility.py (cached daily)</Source>
                  </div>
                </Panel>
              </div>
            </>
          );
        }}
      </DataState>
    </div>
  );
}
