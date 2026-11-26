import { useStrategies } from "../services/api";
import { Badge, Callout, DataState, KV, PageHead, Panel, Table, Val, type Tone } from "../components/ui";
import type { StrategyRow } from "../types/api";
import { dir, num, pct } from "../utils/format";

function statusTone(s: string): Tone {
  if (/^PAPER/.test(s)) return "accent";
  if (/reject/i.test(s)) return "bad";
  if (/passed/i.test(s)) return "ok";
  return "";
}

function policyTone(p: string | undefined): Tone {
  return p === "current policy" ? "ok" : "warn";
}

export default function StrategyLab() {
  const q = useStrategies();
  return (
    <div className="page stack">
      <PageHead
        crumbs="Research"
        title="Strategy Lab"
        lede="Every strategy the lab has evaluated, its gate result and the evidence behind it. Only the ensemble runs, and only in paper and shadow."
      />
      <Callout tone="warn" title="Read the evidence label.">
        Rows marked "historical (looser risk)" were measured with 1% risk per trade and 3 positions, not the current 0.5% / 2 policy. Their returns are not comparable with the current-policy row.
      </Callout>
      <DataState q={q} rows={6}>
        {(d) => {
          const ens = d.rows.find((r) => r.id === "ensemble");
          const lgb = d.rows.find((r) => r.id === "lightgbm");
          return (
            <>
              <Panel title="Candidates" flush>
                <Table<StrategyRow>
                  caption="Strategy candidates and gate results"
                  rows={d.rows}
                  cols={[
                    { key: "label", label: "Strategy", render: (r) => <strong>{r.label}</strong> },
                    { key: "status", label: "Status", render: (r) => <Badge tone={statusTone(r.status)}>{r.status}</Badge> },
                    { key: "evidence_policy", label: "Evidence", render: (r) => <Badge tone={policyTone(r.evidence_policy)}>{r.evidence_policy ?? "—"}</Badge> },
                    { key: "ret", label: "Return", num: true, render: (r) => <Val v={pct(r.metrics?.return_pct)} tone={dir(r.metrics?.return_pct)} /> },
                    { key: "dd", label: "Max DD", num: true, render: (r) => <Val v={pct(r.metrics?.max_drawdown_pct)} /> },
                    { key: "pf", label: "Profit factor", num: true, render: (r) => <Val v={num(r.metrics?.profit_factor)} /> },
                    { key: "tr", label: "Trades", num: true, render: (r) => <Val v={num(r.metrics?.trades, 0)} /> },
                    { key: "wr", label: "Win rate", num: true, render: (r) => <Val v={pct(r.metrics?.win_rate_pct, 1, false)} /> },
                    { key: "mc", label: "P(loss) MC", num: true, render: (r) => <Val v={pct(r.monte_carlo?.p_loss == null ? null : (r.monte_carlo.p_loss as number) * 100, 1, false)} /> },
                    { key: "why", label: "Rejected because", wrap: true, render: (r) => (r.rejected_because?.length ? <span className="muted">{r.rejected_because.join("; ")}</span> : <Val v="—" />) },
                  ]}
                />
              </Panel>
              <div className="grid cols-2">
                {ens ? (
                  <Panel title="Ensemble · current policy" meta={`evidence: ${ens.evidence_tag ?? "—"}`}>
                    <KV
                      items={[
                        ["Return (full window)", <Val v={pct(ens.metrics?.return_pct)} tone={dir(ens.metrics?.return_pct)} />],
                        ["Max drawdown", <Val v={pct(ens.metrics?.max_drawdown_pct)} />],
                        ["Profit factor", <Val v={num(ens.metrics?.profit_factor)} />],
                        ["Trades", <Val v={num(ens.metrics?.trades, 0)} />],
                        ["Sub-period returns", <span>{(ens.subperiod_returns_pct ?? []).map((v) => pct(v, 1)).join("  ") || "—"}</span>],
                        ["Monte Carlo median", <Val v={pct(ens.monte_carlo?.median_ret_pct)} />],
                        ["Monte Carlo 5th pct", <Val v={pct(ens.monte_carlo?.p5_ret_pct)} tone={dir(ens.monte_carlo?.p5_ret_pct)} />],
                        ["Monte Carlo 95th pct drawdown", <Val v={pct(ens.monte_carlo?.p95_dd_pct, 2, false)} />],
                      ]}
                    />
                    <p className="faint section-gap">
                      Monte Carlo reshuffles the backtest's trade sequence; it measures path risk of these trades, not future performance. {num(ens.metrics?.trades, 0)} trades in this run; the readiness gate wants at least 300 out-of-sample trades.
                    </p>
                  </Panel>
                ) : null}
                {lgb ? (
                  <Panel title="LightGBM model" actions={<Badge tone="bad">REJECTED</Badge>}>
                    <p className="muted" style={{ marginTop: 0 }}>
                      The machine-learning model was evaluated and rejected. It is not used by any bot.
                    </p>
                    {lgb.rejected_because?.length ? (
                      <ul className="list">
                        {lgb.rejected_because.map((x) => (
                          <li key={x}>{x}</li>
                        ))}
                      </ul>
                    ) : null}
                    <p className="faint section-gap">Source: MODEL_EVALUATION.md</p>
                  </Panel>
                ) : null}
              </div>
            </>
          );
        }}
      </DataState>
    </div>
  );
}
