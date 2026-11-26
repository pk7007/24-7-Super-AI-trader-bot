import { Fragment } from "react";
import { useReadiness } from "../services/api";
import { Badge, Callout, DataState, KV, Meter, Metric, PageHead, Panel, Strip, Table, Val } from "../components/ui";
import { ago, cell, num } from "../utils/format";

interface DRow {
  name: string;
  weight: number;
  earned: number | null;
  missing: string[];
}

export default function Readiness() {
  const q = useReadiness();
  return (
    <div className="page stack">
      <PageHead
        crumbs="Risk & Operations"
        title="Live Readiness"
        lede="How far the bot is from being allowed to trade real money, scored by bot/readiness.py. This is trading readiness, not the quality of this interface."
      />
      <DataState q={q} rows={8}>
        {(d) => {
          const r = d.report;
          const domains: DRow[] = Object.entries(r.domains ?? {}).map(([name, v]) => ({
            name,
            weight: (v.weight as number) ?? d.weights[name],
            earned: typeof v.earned === "number" ? v.earned : null,
            missing: (v.missing as string[]) ?? [],
          }));
          const pe = (r.paper_evidence ?? {}) as Record<string, number | null>;
          const se = (r.shadow_evidence ?? {}) as Record<string, number | null>;
          const T = d.thresholds;
          return (
            <>
              <Callout tone={r.live_trading_allowed ? "warn" : "bad"} title={r.live_trading_allowed ? "Gate open." : "Live trading not allowed."}>
                {(r.mandatory_blockers ?? []).length} mandatory blockers remain. Moving to live also needs explicit human approval; nothing in this interface can do it.
              </Callout>
              <Strip label="Readiness summary">
                <Metric lg label="Score" value={r.overall_score == null ? "—" : `${r.overall_score}/100`} sub={r.classification} />
                <Metric label="Deployment state" value={d.current_state} />
                <Metric label="Tests at last score" value={cell(r.tests_run)} sub={r.tests_all_passed ? "all passed" : "not all passed"} />
                <Metric label="Scored" value={ago(r.generated_utc)} sub="re-run python -m bot.readiness to refresh" />
              </Strip>
              <Panel title="Deployment path">
                <div className="pipeline" role="list" aria-label="Deployment states">
                  {d.states.map((s, i) => {
                    const cur = d.states.indexOf(d.current_state);
                    const cls = s === d.current_state ? "current" : i < cur ? "done" : "";
                    const live = d.live_states?.includes(s);
                    return (
                      <Fragment key={s}>
                        {i > 0 ? <span className="arrow" aria-hidden>→</span> : null}
                        <span role="listitem" className={`stage ${cls} ${live ? "live" : ""}`} aria-current={s === d.current_state ? "step" : undefined}>
                          {s}
                        </span>
                      </Fragment>
                    );
                  })}
                </div>
                <p className="faint section-gap">Dashed stages involve real money. Any state can drop to {(d.anytime_states ?? []).join(" / ") || "—"}.</p>
              </Panel>
              <div className="grid cols-main-side">
                <Panel title="Score by domain" flush>
                  <Table<DRow>
                    caption="Readiness score by domain"
                    rows={domains}
                    cols={[
                      { key: "name", label: "Domain", render: (x) => <strong>{x.name}</strong> },
                      { key: "s", label: "Earned", num: true, render: (x) => <span>{x.earned ?? "—"} / {x.weight}</span> },
                      { key: "m", label: "", render: (x) => <div style={{ width: 100 }}><Meter value={x.earned == null ? null : (x.earned / x.weight) * 100} label={`${x.name} score`} progress /></div> },
                      { key: "missing", label: "Missing evidence", wrap: true, render: (x) => <span className="muted">{x.missing.join("; ") || "—"}</span> },
                    ]}
                  />
                </Panel>
                <div className="stack">
                  <Panel title="Evidence vs thresholds">
                    <KV
                      items={[
                        ["Paper days", <span>{num(pe.days_running, 1)} / {T.paper_days}</span>],
                        ["Paper trades", <span>{cell(pe.completed_trades)} / {T.paper_trades}</span>],
                        ["Paper profit factor", <span><Val v={num(pe.profit_factor)} /> / ≥{T.profit_factor}</span>],
                        ["Shadow days", <span>{num(se.days_running, 1)} / {T.shadow_days}</span>],
                        ["Max drawdown allowed", <span>{T.max_dd_pct}%</span>],
                        ["Out-of-sample trades", <span>≥{T.oos_trades}</span>],
                      ]}
                    />
                  </Panel>
                  <Panel title="Mandatory blockers" meta={`${(r.mandatory_blockers ?? []).length}`}>
                    <ul className="list">
                      {(r.mandatory_blockers ?? []).map((b) => (
                        <li key={b}>{b}</li>
                      ))}
                    </ul>
                  </Panel>
                </div>
              </div>
              <span className="faint">
                <Badge tone="outline">{String(d.source ?? "")}</Badge> {String(d.note ?? "")}
              </span>
            </>
          );
        }}
      </DataState>
    </div>
  );
}
