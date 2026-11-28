import { Link } from "react-router-dom";
import { useHealth, useMarkets, useOverview } from "../services/api";
import { Badge, Callout, DataState, Fetching, KV, Metric, PageHead, Panel, Source, Status, Strip, Table, Val, heartbeatTone } from "../components/ui";
import { Decision, KillSwitchTable } from "./shared";
import type { ModeOverview, Row } from "../types/api";
import { ago, dir, minutes, pct, price, usd } from "../utils/format";

const sentence = (t: string) => t.charAt(0).toUpperCase() + t.slice(1);

function ModeCard({ m }: { m: ModeOverview }) {
  const hb = m.heartbeat;
  return (
    <Panel
      title={<span style={{ textTransform: "capitalize" }}>{m.mode} bot</span>}
      meta="simulated"
      actions={<Status tone={heartbeatTone(hb.status)}>{hb.status}</Status>}
    >
      <div className="stack">
        <KV
          items={[
            ["Equity", <Val v={usd(m.equity.value)} />],
            ["Realized P&L", <Val v={usd(m.realized_pnl)} tone={dir(m.realized_pnl)} />],
            ["Open positions", <Val v={m.open_positions == null ? "—" : String(m.open_positions)} />],
            ["Last candle logged", <span>{ago(hb.last_candle_logged_utc)}</span>],
            ["New entries", m.entries_halted === true ? <Badge tone="bad">HALTED</Badge> : m.entries_halted === false ? <Badge tone="ok">allowed</Badge> : <Badge tone="warn">unknown</Badge>],
          ]}
        />
        <div className="row">
          <span className="faint">Last decisions</span>
          {Object.entries(hb.last_decisions ?? {}).map(([s, d]) => (
            <span key={s} className="row" style={{ gap: 4 }}>
              <span className="mono faint">{s}</span>
              <Decision d={d} />
            </span>
          ))}
          {!hb.last_decisions ? <Val v="—" /> : null}
        </div>
      </div>
      <div className="section-gap" style={{ margin: "var(--sp-3) calc(-1 * var(--sp-3)) calc(-1 * var(--sp-3))", borderTop: "1px solid var(--c-border)" }}>
        <KillSwitchTable ks={m.kill_switches} />
      </div>
    </Panel>
  );
}

export default function CommandCenter() {
  const ov = useOverview();
  const mk = useMarkets();
  const hl = useHealth();
  return (
    <div className="page stack">
      <PageHead
        crumbs="Workspace"
        title="Command Center"
        lede="State of the paper and shadow bots, the market they watch, and how far the project is from live trading. Everything here is read-only and comes from the bots' own files."
        actions={<Fetching q={ov} />}
      />
      <DataState q={ov} rows={4}>
        {(d) => {
          const p = d.modes.paper;
          const s = d.modes.shadow;
          const down = [p, s].filter((m) => m.heartbeat.status !== "alive");
          return (
            <>
              {down.length ? (
                <Callout tone="bad" title="Bot not reporting.">
                  {down.map((m) => `${m.mode}: ${m.heartbeat.status} (last log ${minutes(m.heartbeat.age_min)} ago)`).join("; ")}. The engine logs once per 15-minute candle.
                </Callout>
              ) : null}
              <Callout tone="info" title="Live trading is disabled.">
                {sentence(d.live_trading.replace(/^disabled:\s*/i, ""))}. Deployment state <strong>{d.readiness.deployment_state}</strong>; readiness {d.readiness.score ?? "—"}/100 ({d.readiness.classification ?? "unknown"}).{" "}
                <Link to="/readiness">See what blocks live</Link>.
              </Callout>
              <Strip label="Key figures">
                <Metric lg label="Paper equity" value={usd(p.equity.value)} sub={p.equity.basis} />
                <Metric lg label="Shadow equity" value={usd(s.equity.value)} sub={s.equity.basis} />
                <Metric label="Open positions" value={p.open_positions == null ? "—" : `${p.open_positions} / ${s.open_positions ?? "—"}`} sub="paper / shadow" />
                <Metric label="Paper fills" value={p.fill_count == null ? "—" : String(p.fill_count)} sub="since start" />
                <Metric label="Daily limit used" value={pct(p.kill_switches.daily?.utilization_pct, 0, false)} sub={`of ${pct(p.kill_switches.daily?.limit_pct, 1, false)} (paper)`} />
                <Metric label="Readiness" value={d.readiness.score == null ? "—" : `${d.readiness.score}/100`} sub="trading readiness, not UI quality" tip="Scored by bot/readiness.py" />
              </Strip>
              <div className="grid cols-2">
                <ModeCard m={p} />
                <ModeCard m={s} />
              </div>
            </>
          );
        }}
      </DataState>

      <div className="grid cols-main-side">
        <Panel title="Markets" meta="15m candles, signal venue Binance" flush actions={<Link to="/market">Open terminal</Link>}>
          <DataState q={mk}>
            {(d) => (
              <Table<Row>
                caption="Markets watched by the bot"
                rows={d.rows}
                cols={[
                  { key: "symbol", label: "Symbol", render: (r) => <strong>{String(r.symbol)}</strong> },
                  { key: "last_close", label: "Last close (USDT)", num: true, render: (r) => <Val v={price(r.last_close)} /> },
                  { key: "change_24h_pct", label: "24h", num: true, render: (r) => <Val v={pct(r.change_24h_pct)} tone={dir(r.change_24h_pct)} /> },
                  { key: "data_age_min", label: "Data age", num: true, render: (r) => <Val v={minutes(r.data_age_min)} /> },
                  { key: "paper_decision", label: "Paper", render: (r) => <Decision d={r.paper_decision as string | undefined} /> },
                  { key: "shadow_decision", label: "Shadow", render: (r) => <Decision d={r.shadow_decision as string | undefined} /> },
                  { key: "execution_instrument", label: "Executes as", render: (r) => <span className="mono faint">{String(r.execution_instrument ?? "—")}</span> },
                ]}
              />
            )}
          </DataState>
        </Panel>
        <Panel title="Operations (24h)" flush actions={<Link to="/health">Health</Link>}>
          <DataState q={hl}>
            {(d) => (
              <div className="panel-body">
                <KV
                  items={(["paper", "shadow"] as const).flatMap((m) => {
                    const h = d.modes[m] as Record<string, unknown> | undefined;
                    if (!h) return [[`${m}`, <Val v="—" />]] as [string, React.ReactNode][];
                    const got = h.candles_last_24h as number;
                    const exp = h.expected_candles_24h as number;
                    return [
                      [`${m}: candles completed`, <span className={got < exp ? "down" : undefined}>{got} / {exp}</span>],
                      [`${m}: step failures`, <span className={(h.step_failures_24h as number) > 0 ? "down" : undefined}>{String(h.step_failures_24h)}</span>],
                    ] as [string, React.ReactNode][];
                  })}
                />
                <div className="section-gap">
                  <Source>state/*.log, read-only</Source>
                </div>
              </div>
            )}
          </DataState>
        </Panel>
      </div>
    </div>
  );
}
