import { useMemo, useState } from "react";
import { useSignals } from "../services/api";
import { Badge, Callout, DataState, Fetching, Metric, PageHead, Panel, Seg, Strip, Table, Val } from "../components/ui";
import { Decision, ModeSeg, useModeParam } from "./shared";
import type { SignalRow } from "../types/api";
import { usd, utc } from "../utils/format";

const SYMS = ["BTC", "ETH", "SOL"];

export default function Signals() {
  const [mode, setMode] = useModeParam();
  const [only, setOnly] = useState<"all" | "action">("all");
  const q = useSignals(mode);
  const stats = useMemo(() => {
    const rows = q.data?.data.rows ?? [];
    const c = { BUY: 0, SELL: 0, out: 0, noData: 0 };
    for (const r of rows) {
      if (r.no_data) c.noData++;
      for (const s of SYMS) {
        const d = r.decisions?.[s];
        if (d === "BUY") c.BUY++;
        else if (d === "SELL") c.SELL++;
        else c.out++;
      }
    }
    return { n: rows.length, ...c };
  }, [q.data]);

  return (
    <div className="page stack">
      <PageHead
        crumbs="Trading"
        title="Signals"
        lede="The engine's decision for each symbol on every closed 15-minute candle, read from its log."
        actions={
          <>
            <ModeSeg mode={mode} set={setMode} />
            <Seg
              label="Filter"
              value={only}
              onChange={setOnly}
              options={[
                { v: "all", label: "All candles" },
                { v: "action", label: "Buy / sell only" },
              ]}
            />
            <Fetching q={q} />
          </>
        }
      />
      <Callout tone="info" title="No probabilities.">
        The strategy is rule-based (EMA trend + time-series momentum). It outputs buy, sell or stay out; it does not produce a confidence score, so none is shown.
      </Callout>
      <Strip label="Signal counts">
        <Metric label="Candles logged" value={String(stats.n)} sub="in the log tail read" />
        <Metric label="BUY decisions" value={String(stats.BUY)} />
        <Metric label="SELL decisions" value={String(stats.SELL)} />
        <Metric label="Stay out" value={String(stats.out)} />
        <Metric label="Candles with no data" value={String(stats.noData)} />
      </Strip>
      <Panel title="Decision log" meta={q.data?.data.source} flush>
        <DataState q={q}>
          {(d) => {
            const rows = only === "all" ? d.rows : d.rows.filter((r) => SYMS.some((s) => r.decisions?.[s] === "BUY" || r.decisions?.[s] === "SELL"));
            return (
              <Table<SignalRow>
                caption="Engine decisions per candle"
                rows={rows}
                maxHeight={620}
                empty={only === "action" ? "No buy or sell decisions in the logged period." : "No candles logged yet."}
                cols={[
                  { key: "logged_utc", label: "Logged (UTC)", render: (r) => <span className="mono">{utc(r.logged_utc)}</span> },
                  { key: "candle_label_utc", label: "Candle", render: (r) => <span className="mono">{r.candle_label_utc ?? "—"}</span> },
                  ...SYMS.map((s) => ({ key: s, label: s, render: (r: SignalRow) => <Decision d={r.decisions?.[s]} /> })),
                  { key: "held", label: "Held" },
                  { key: "equity", label: "Equity", num: true, render: (r) => <Val v={usd(r.equity)} /> },
                  { key: "no_data", label: "Data", render: (r) => (r.no_data ? <Badge tone="warn">no data</Badge> : <Badge tone="outline">ok</Badge>) },
                ]}
              />
            );
          }}
        </DataState>
      </Panel>
    </div>
  );
}
