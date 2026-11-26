// Tables for positions, fills and shadow intents, shared by ModeWorkspace and Orders.
import type { Row } from "../types/api";
import { Badge, Table, Val } from "../components/ui";
import { cell, dir, price, qty, usd, utc } from "../utils/format";

const emptyText = (availability: string | undefined, what: string) =>
  availability && availability !== "ok" ? `Not available: ${availability}.` : `No ${what} yet.`;

export function PositionsTable({ rows, availability }: { rows: Row[]; availability?: string }) {
  return (
    <Table<Row>
      caption="Open positions"
      rows={rows}
      empty={emptyText(availability, "open positions")}
      cols={[
        { key: "symbol", label: "Instrument", render: (r) => <strong>{String(r.symbol)}</strong> },
        { key: "side_label", label: "Side", render: (r) => <Badge tone={r.side_label === "LONG" ? "ok" : "bad"}>{String(r.side_label)}</Badge> },
        { key: "coins", label: "Quantity (coins)", num: true, render: (r) => <Val v={qty(r.coins)} /> },
        { key: "contracts", label: "Engine units", num: true, render: (r) => <Val v={cell(r.contracts)} /> },
        { key: "entry", label: "Entry", num: true, render: (r) => <Val v={price(r.entry)} /> },
        { key: "stop", label: "Stop", num: true, render: (r) => <Val v={price(r.stop)} /> },
        { key: "notional_usd", label: "Notional", num: true, render: (r) => <Val v={usd(r.notional_usd)} /> },
        { key: "risk_to_stop_usd", label: "Risk to stop", num: true, render: (r) => <Val v={usd(r.risk_to_stop_usd)} /> },
        { key: "opened_ts", label: "Opened", render: (r) => <span className="mono">{utc(r.opened_ts as string)}</span> },
      ]}
    />
  );
}

export function FillsTable({ rows, availability }: { rows: Row[]; availability?: string }) {
  return (
    <Table<Row>
      caption="Simulated fills"
      rows={rows}
      maxHeight={420}
      empty={emptyText(availability, "fills")}
      cols={[
        { key: "ts", label: "Time (UTC)", render: (r) => <span className="mono">{utc(r.ts as string)}</span> },
        { key: "symbol", label: "Instrument" },
        { key: "side", label: "Side", render: (r) => <Badge tone={String(r.side).toLowerCase() === "buy" ? "ok" : "bad"}>{String(r.side).toUpperCase()}</Badge> },
        { key: "qty", label: "Qty", num: true, render: (r) => <Val v={qty(r.qty)} /> },
        { key: "price", label: "Price", num: true, render: (r) => <Val v={price(r.price)} /> },
        { key: "fee", label: "Fee", num: true, render: (r) => <Val v={usd(r.fee, 4)} /> },
        { key: "realized_pnl", label: "Realized P&L", num: true, render: (r) => <Val v={usd(r.realized_pnl)} tone={dir(r.realized_pnl)} /> },
        { key: "reason", label: "Reason" },
      ]}
    />
  );
}

export function IntentsTable({ rows, availability }: { rows: Row[]; availability?: string }) {
  const keys = rows.length ? Object.keys(rows[0]) : [];
  return (
    <Table<Row>
      caption="Shadow order intentions"
      rows={rows}
      maxHeight={420}
      empty={emptyText(availability, "order intentions")}
      cols={keys.map((k) => ({ key: k, label: k.replace(/_/g, " ") }))}
    />
  );
}
