import { useLedger } from "../services/api";
import { Callout, DataState, Fetching, Metric, ModeBanner, PageHead, Panel, Strip, Table, Val } from "../components/ui";
import { ModeSeg, useModeParam } from "./shared";
import type { Row } from "../types/api";
import { dir, price, qty, usd, utc } from "../utils/format";

const n = (v: unknown) => (v === null || v === undefined || v === "" ? NaN : Number(v));

export default function Ledger() {
  const [mode, setMode] = useModeParam();
  const q = useLedger(mode);
  return (
    <div className="page stack">
      <PageHead
        crumbs="Finance"
        title="Ledger & Tax"
        lede="Every fill appended to trades_ledger.csv, the record India's crypto tax rules need. Paper and shadow ledgers are simulations."
        actions={
          <>
            <ModeSeg mode={mode} set={setMode} />
            <Fetching q={q} />
          </>
        }
      />
      <ModeBanner mode={mode} />
      <Callout tone="warn" title="Estimates only.">
        Tax figures assume a flat 30% on net gains and 1% TDS on each sale, with no loss set-off, as India's rules for virtual digital assets are commonly read. Confirm with a chartered accountant before filing.
      </Callout>
      <DataState q={q} rows={5}>
        {(d) => {
          const rows = d.rows;
          const pnl = rows.map((r) => n(r.realized_pnl)).filter(Number.isFinite);
          const gains = pnl.filter((v) => v > 0).reduce((a, b) => a + b, 0);
          const fees = rows.map((r) => n(r.fee)).filter(Number.isFinite).reduce((a, b) => a + b, 0);
          const sales = rows.filter((r) => String(r.side).toLowerCase() === "sell");
          const saleValue = sales.reduce((a, r) => a + (Number.isFinite(n(r.qty) * n(r.price)) ? n(r.qty) * n(r.price) : 0), 0);
          const has = rows.length > 0;
          return (
            <>
              <Strip label="Ledger totals">
                <Metric label="Fills" value={d.availability && d.availability !== "ok" ? "—" : String(rows.length)} sub={has ? undefined : d.availability} />
                <Metric label="Net realized P&L" value={has ? usd(pnl.reduce((a, b) => a + b, 0)) : "—"} tone={has ? dir(pnl.reduce((a, b) => a + b, 0)) : ""} />
                <Metric label="Fees paid" value={has ? usd(fees, 4) : "—"} />
                <Metric label="Est. tax (30% of gains)" value={has ? usd(gains * 0.3) : "—"} sub="losses not set off" />
                <Metric label="Est. TDS (1% of sales)" value={has ? usd(saleValue * 0.01, 4) : "—"} />
              </Strip>
              <Panel title="Ledger" meta={d.source} flush>
                <Table<Row>
                  caption="Trade ledger"
                  rows={rows}
                  maxHeight={560}
                  empty={d.availability && d.availability !== "ok" ? `Not available: ${d.availability}.` : "No fills recorded yet."}
                  cols={[
                    { key: "timestamp", label: "Time (UTC)", render: (r) => <span className="mono">{utc(r.timestamp as string)}</span> },
                    { key: "pair", label: "Pair" },
                    { key: "side", label: "Side" },
                    { key: "qty", label: "Qty", num: true, render: (r) => <Val v={qty(n(r.qty))} /> },
                    { key: "price", label: "Price", num: true, render: (r) => <Val v={price(n(r.price))} /> },
                    { key: "fee", label: "Fee", num: true, render: (r) => <Val v={usd(n(r.fee), 4)} /> },
                    { key: "realized_pnl", label: "Realized P&L", num: true, render: (r) => <Val v={usd(n(r.realized_pnl))} tone={dir(n(r.realized_pnl))} /> },
                    { key: "reason", label: "Reason" },
                    { key: "order_id", label: "Order ID", render: (r) => <span className="mono faint">{String(r.order_id ?? "—")}</span> },
                  ]}
                />
              </Panel>
            </>
          );
        }}
      </DataState>
    </div>
  );
}
