import { useMemo } from "react";
import { Link } from "react-router-dom";
import { useFills, useIntents, useOverview, usePositions, useSignals, type Mode } from "../services/api";
import { Badge, Callout, DataState, Fetching, Metric, ModeBanner, PageHead, Panel, Source, Status, Strip, heartbeatTone } from "../components/ui";
import { LineChart } from "../components/charts/Charts";
import { KillSwitchTable } from "./shared";
import { PositionsTable, FillsTable, IntentsTable } from "./tables";
import { ago, dir, minutes, usd } from "../utils/format";

export default function ModeWorkspace({ mode }: { mode: Mode }) {
  const ov = useOverview();
  const pos = usePositions(mode);
  const fills = useFills(mode);
  const sig = useSignals(mode);
  const intents = useIntents();
  const equityPts = useMemo(() => (sig.data?.data.rows ?? []).slice().reverse().map((r) => ({ t: r.logged_utc, v: r.equity })), [sig.data]);
  const title = mode === "paper" ? "Paper Trading" : "Shadow Trading";

  return (
    <div className="page stack">
      <PageHead
        crumbs="Trading"
        title={title}
        lede={
          mode === "paper"
            ? "The paper bot runs the live strategy against real Binance candles and fills orders in a simulated broker."
            : "The shadow bot runs the same strategy and records the exact orders it would send, without sending them."
        }
        actions={<Fetching q={ov} />}
      />
      <ModeBanner mode={mode} />
      <DataState q={ov} rows={2}>
        {(d) => {
          const m = d.modes[mode];
          if (!m) return <Callout tone="warn">No data for this mode.</Callout>;
          return (
            <>
              {m.accounting_halted === true ? (
                <Callout tone="bad" title="Accounting reconciliation required.">
                  New entries are halted because a fill could not be durably recorded. Protection and emergency exits continue. Verify the exchange account and repair the ledger before clearing the safety halt.
                </Callout>
              ) : null}
              {m.heartbeat.status !== "alive" ? (
                <Callout tone="bad" title={`Bot ${m.heartbeat.status}.`}>
                  Last engine log {minutes(m.heartbeat.age_min)} ago (threshold {m.heartbeat.threshold_min} min). Figures below may be out of date.
                </Callout>
              ) : null}
              <Strip label={`${mode} figures`}>
                <Metric lg label="Equity" value={usd(m.equity.value)} sub={m.equity.basis} />
                <Metric label="Realized P&L" value={usd(m.realized_pnl)} tone={dir(m.realized_pnl)} />
                <Metric label="Fills" value={m.fill_count == null ? "—" : String(m.fill_count)} />
                <Metric label="Open positions" value={m.open_positions == null ? "—" : String(m.open_positions)} />
                <Metric label="Open risk to stops" value={usd(m.open_risk_usd)} />
                <Metric label="Heartbeat" value={m.heartbeat.status} sub={`last candle ${ago(m.heartbeat.last_candle_logged_utc)}`} />
              </Strip>
              <div className="grid cols-2">
                <Panel title="Equity per closed candle" meta="from the engine's own log lines" actions={<Status tone={heartbeatTone(m.heartbeat.status)}>{m.heartbeat.status}</Status>}>
                  {equityPts.length > 1 ? (
                    <LineChart points={equityPts} area label={`${mode} equity over time`} />
                  ) : (
                    <div className="state">Not enough logged candles yet to draw equity.</div>
                  )}
                  <div className="section-gap">
                    <Source>state/{mode}.log</Source>
                  </div>
                </Panel>
                <Panel title="Loss limits" flush>
                  <KillSwitchTable ks={m.kill_switches} />
                </Panel>
              </div>
            </>
          );
        }}
      </DataState>
      <Panel title="Open positions" meta={pos.data?.data.source} flush>
        <DataState q={pos}>{(d) => <PositionsTable rows={d.rows} availability={d.availability} />}</DataState>
      </Panel>
      <Panel title="Fills" meta="simulated" flush actions={<Link to={`/ledger?mode=${mode}`}>Ledger</Link>}>
        <DataState q={fills}>{(d) => <FillsTable rows={d.rows} availability={d.availability} />}</DataState>
      </Panel>
      {mode === "shadow" ? (
        <Panel title="Order intentions" meta="what would have been sent" flush>
          <DataState q={intents}>{(d) => <IntentsTable rows={d.rows} availability={d.availability} />}</DataState>
        </Panel>
      ) : null}
      <span className="faint">
        <Badge tone="outline">read-only</Badge> This workspace cannot place, cancel or modify orders.
      </span>
    </div>
  );
}

