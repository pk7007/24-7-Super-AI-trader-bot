import { useRisk } from "../services/api";
import { Badge, Callout, DataState, PageHead, Panel, Table, Val } from "../components/ui";
import { KillSwitchTable } from "./shared";
import type { Cell } from "../types/api";
import { cell, frac, pct } from "../utils/format";

const FRACTION_KEYS = new Set(["risk_per_trade", "daily_loss_limit", "weekly_loss_limit", "monthly_loss_limit", "max_venue_deviation", "taker_fee", "slippage", "stop_slippage"]);
const LABELS: Record<string, string> = {
  risk_per_trade: "Risk per trade",
  max_positions: "Max open positions",
  daily_loss_limit: "Daily loss limit",
  weekly_loss_limit: "Weekly loss limit",
  monthly_loss_limit: "Monthly loss limit",
  max_leverage: "Max leverage",
  stop_atr: "Stop distance (× ATR)",
  min_order_inr: "Minimum order (INR)",
  max_venue_deviation: "Max signal/execution price gap",
  taker_fee: "Taker fee",
  gst: "GST multiplier on fees",
  slippage: "Entry slippage",
  stop_slippage: "Stop slippage",
  usdt_inr: "USDT/INR rate",
  market: "Market profile",
  allow_short: "Shorting",
  strategy: "Strategy",
  start_equity: "Configured start equity (default)",
};

const show = (k: string, v: Cell | undefined) => (v === undefined ? "—" : FRACTION_KEYS.has(k) && typeof v === "number" ? frac(v, k.includes("fee") || k.includes("slippage") ? 3 : 2) : cell(v));

interface PRow {
  key: string;
  eff: Cell | undefined;
  ceil: Cell | undefined;
}

export default function RiskCenter() {
  const q = useRisk();
  return (
    <div className="page stack">
      <PageHead crumbs="Risk & Operations" title="Risk Management" lede="The limits the bots actually run with, the hard ceilings in code, and which protections are only simulated." />
      <DataState q={q} rows={8}>
        {(d) => {
          const rows: PRow[] = Object.keys(d.effective).map((k) => ({ key: k, eff: d.effective[k], ceil: d.policy_ceiling[k] }));
          return (
            <>
              {d.discrepancies.map((x) => (
                <Callout key={x} tone="warn" title="Policy discrepancy.">
                  {x}
                </Callout>
              ))}
              <div className="grid cols-main-side">
                <Panel title="Effective configuration" meta="paper and shadow share it" flush>
                  <Table<PRow>
                    caption="Effective risk configuration versus policy ceiling"
                    rows={rows}
                    cols={[
                      { key: "key", label: "Setting", render: (r) => <span>{LABELS[r.key] ?? r.key}</span> },
                      { key: "eff", label: "Effective", num: true, render: (r) => <Val v={show(r.key, r.eff)} /> },
                      { key: "ceil", label: "Hard ceiling", num: true, render: (r) => <Val v={show(r.key, r.ceil)} /> },
                      {
                        key: "s",
                        label: "",
                        render: (r) =>
                          r.ceil === undefined ? null : r.eff === r.ceil ? <Badge tone="outline">at ceiling</Badge> : <Badge tone="ok">stricter</Badge>,
                      },
                    ]}
                  />
                </Panel>
                <div className="stack">
                  <Panel title="Costs per round trip">
                    <div className="metric-value lg">
                      <Val v={pct(d.round_trip_cost_pct, 3, false)} />
                    </div>
                    <p className="faint">2 × taker fee × GST + entry slippage + stop slippage. Position sizing includes this cost, so a stopped-out trade loses about the risk budget, not more.</p>
                  </Panel>
                  <Callout tone="warn" title="Nothing here is verified on a real exchange.">
                    No live venue is connected, so every protection below is checked by unit tests and the simulated paper broker at most.
                  </Callout>
                </div>
              </div>
              <Panel title="Protections" flush>
                <Table
                  caption="Protections and how each is verified"
                  rows={d.protections}
                  cols={[
                    { key: "name", label: "Protection", render: (r) => <strong>{String(r.name)}</strong> },
                    { key: "status", label: "How it works", wrap: true, render: (r) => <span className="muted">{String(r.status)}</span> },
                    {
                      key: "verified_by",
                      label: "Verified by",
                      wrap: true,
                      render: (r) => {
                        const v = String(r.verified_by ?? "not stated");
                        return <Badge tone={/assumption|not active|never on/.test(v) ? "warn" : "outline"}>{v}</Badge>;
                      },
                    },
                  ]}
                />
              </Panel>
              <div className="grid cols-2">
                {Object.entries(d.modes).map(([m, ks]) => (
                  <Panel key={m} title={<span style={{ textTransform: "capitalize" }}>{m} loss limits</span>} flush>
                    <KillSwitchTable ks={ks} />
                  </Panel>
                ))}
              </div>
              <span className="faint">
                <Badge tone="outline">read-only</Badge> Risk settings cannot be changed from this interface. Changes go through code review and the readiness gate.
              </span>
            </>
          );
        }}
      </DataState>
    </div>
  );
}
