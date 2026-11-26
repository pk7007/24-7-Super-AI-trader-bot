import { useMemo } from "react";
import { useBacktests } from "../services/api";
import { Badge, Callout, DataState, KV, PageHead, Panel, Table, Val } from "../components/ui";
import { LineChart } from "../components/charts/Charts";
import type { LabReport } from "../types/api";
import { dir, frac, num, pct, usd, utc } from "../utils/format";

type LabRow = LabReport & { ens: LabReport["candidates"][string] | undefined };

export default function Backtesting() {
  const q = useBacktests();
  const eq = q.data?.data.historical_equity;
  const eqPts = useMemo(() => (eq?.points ?? []).map((p) => ({ t: p.t, v: p.equity })), [eq]);
  const ddPts = useMemo(() => (eq?.drawdown ?? []).map((p) => ({ t: p.t, v: p.drawdown_pct })), [eq]);

  return (
    <div className="page stack">
      <PageHead crumbs="Research" title="Backtesting" lede="Lab reports on cached Binance history, with every run labelled by the risk settings it used." />
      <DataState q={q} rows={8}>
        {(d) => {
          const rows: LabRow[] = d.lab_reports.map((r) => ({ ...r, ens: r.candidates?.ensemble }));
          const current = rows.filter((r) => r.classification === "current policy");
          // in-sample runs ordered by fee (fee stress test), then out-of-sample holdout runs
          const isHoldout = (r: LabRow) => r.tag.startsWith("holdout");
          const ordered = current.slice().sort((a, b) => Number(isHoldout(a)) - Number(isHoldout(b)) || (a.taker_fee ?? 0) - (b.taker_fee ?? 0));
          const m = d.historical_equity.metrics as Record<string, number> | null | undefined;
          return (
            <>
              <Panel title="Current-policy runs" meta="0.5% risk per trade, 2 positions, cost-inclusive sizing" flush>
                <Table<LabRow>
                  caption="Current policy backtests"
                  rows={ordered}
                  empty="No current-policy runs recorded."
                  cols={[
                    { key: "tag", label: "Run", render: (r) => <span className="mono">{r.tag}</span> },
                    { key: "kind", label: "Sample", render: (r) => (isHoldout(r) ? <Badge tone="info">out-of-sample</Badge> : <Badge tone="outline">in-sample</Badge>) },
                    { key: "window", label: "Window", render: (r) => <span className="mono faint">{r.window ?? "—"}</span> },
                    { key: "fee", label: "Taker fee", num: true, render: (r) => <Val v={frac(r.taker_fee, 2)} /> },
                    { key: "ret", label: "Return", num: true, render: (r) => <Val v={pct(r.ens?.full?.return_pct)} tone={dir(r.ens?.full?.return_pct)} /> },
                    { key: "dd", label: "Max DD", num: true, render: (r) => <Val v={pct(r.ens?.full?.max_drawdown_pct)} /> },
                    { key: "pf", label: "PF", num: true, render: (r) => <Val v={num(r.ens?.full?.profit_factor)} /> },
                    { key: "tr", label: "Trades", num: true, render: (r) => <Val v={num(r.ens?.full?.trades, 0)} /> },
                    { key: "gate", label: "Gate", render: (r) => (r.ens?.promote ? <Badge tone="ok">pass</Badge> : r.ens ? <Badge tone="bad">fail</Badge> : <Val v="—" />) },
                  ]}
                />
              </Panel>

              <Panel title="Historical equity curve" meta={d.historical_equity.classification} actions={<Badge tone="warn">HISTORICAL · LOOSER RISK</Badge>}>
                <Callout tone="warn" title="Not the current policy.">
                  This 2023–2026 curve used 1% risk per trade and 3 positions (perpetual-era settings). It shows the strategy's shape, not what the current bot would have earned.
                </Callout>
                {eqPts.length ? (
                  <>
                    <div className="section-gap">
                      <LineChart points={eqPts} area height={260} label="Historical backtest equity, looser risk settings" />
                    </div>
                    <div className="section-gap">
                      <LineChart points={ddPts} tone="bear" height={140} suffix="%" logo={false} label="Historical backtest drawdown percent" />
                      <p className="faint">
                        Charts: <a href="https://www.tradingview.com/" target="_blank" rel="noreferrer noopener">TradingView Lightweight Charts</a> (Apache-2.0).
                      </p>
                    </div>
                  </>
                ) : (
                  <div className="state">Equity curve not available: {d.historical_equity.availability}.</div>
                )}
                {m ? (
                  <div className="grid cols-3 section-gap">
                    <KV
                      items={[
                        ["Return", <Val v={pct(m.return_pct)} tone={dir(m.return_pct)} />],
                        ["Max drawdown", <Val v={pct(m.max_drawdown_pct)} />],
                        ["Sharpe (daily, ann.)", <Val v={num(m.sharpe_daily_annualised)} />],
                      ]}
                    />
                    <KV
                      items={[
                        ["Trades", <Val v={num(m.trades, 0)} />],
                        ["Win rate", <Val v={pct(m.win_rate_pct, 1, false)} />],
                        ["Profit factor", <Val v={num(m.profit_factor)} />],
                      ]}
                    />
                    <KV
                      items={[
                        ["Fees paid", <Val v={usd(m.fees_paid_usd)} />],
                        ["Days", <Val v={num(m.days, 0)} />],
                        ["Generated", <span className="mono">{utc(d.historical_equity.generated_utc as string | undefined)}</span>],
                      ]}
                    />
                  </div>
                ) : null}
              </Panel>

              <Panel title="All lab reports" meta={`${rows.length} reports · ensemble shown where present`} flush>
                <Table<LabRow>
                  caption="All lab reports"
                  rows={rows}
                  maxHeight={520}
                  cols={[
                    { key: "tag", label: "Report", render: (r) => <span className="mono">{r.tag}</span> },
                    { key: "classification", label: "Risk settings", wrap: true, render: (r) => <Badge tone={r.classification === "current policy" ? "ok" : "warn"}>{r.classification === "current policy" ? "current policy" : "historical"}</Badge> },
                    { key: "market", label: "Market" },
                    { key: "n", label: "Candidates", num: true, render: (r) => <span>{Object.keys(r.candidates ?? {}).length}</span> },
                    { key: "ret", label: "Ensemble return", num: true, render: (r) => <Val v={pct(r.ens?.full?.return_pct)} tone={dir(r.ens?.full?.return_pct)} /> },
                    { key: "dd", label: "DD", num: true, render: (r) => <Val v={pct(r.ens?.full?.max_drawdown_pct)} /> },
                    { key: "pf", label: "PF", num: true, render: (r) => <Val v={num(r.ens?.full?.profit_factor)} /> },
                    { key: "gen", label: "Generated", render: (r) => <span className="mono faint">{utc(r.generated_utc)}</span> },
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
