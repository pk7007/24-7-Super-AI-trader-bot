import { useHealth } from "../services/api";
import { Badge, Callout, DataState, Fetching, KV, Meter, PageHead, Panel, Status, Table, Val, heartbeatTone } from "../components/ui";
import type { HealthMode } from "../types/api";
import { ago, minutes, num, utc } from "../utils/format";

function ModeHealth({ name, h }: { name: string; h: HealthMode }) {
  const got = h.candles_last_24h as number;
  const exp = h.expected_candles_24h as number;
  const cov = exp ? (got / exp) * 100 : null;
  const log = (h.log ?? {}) as { exists?: boolean; size_kb?: number | null };
  const restarts = (h.restarts as string[]) ?? [];
  return (
    <Panel title={<span style={{ textTransform: "capitalize" }}>{name} bot</span>} actions={<Status tone={heartbeatTone(h.heartbeat.status)}>{h.heartbeat.status}</Status>}>
      <KV
        items={[
          ["Last candle logged", <span>{ago(h.heartbeat.last_candle_logged_utc)} <span className="faint">(stale after {h.heartbeat.threshold_min} min)</span></span>],
          [
            "Candles logged, last 24h",
            <span className="row" style={{ justifyContent: "flex-end", flexWrap: "nowrap" }}>
              <span className={got < exp ? "down" : undefined}>
                {got} / {exp}
              </span>
              <span style={{ width: 70 }}>
                <Meter value={cov} label="Candle coverage, last 24 hours" progress />
              </span>
            </span>,
          ],
          ["Step failures, 24h", <span className={(h.step_failures_24h as number) > 0 ? "down" : undefined}>{String(h.step_failures_24h)}</span>],
          ["Feed retries, 24h", <span>{String(h.feed_retries_24h)}</span>],
          ["Warnings, 24h", <span>{String(h.warnings_24h)}</span>],
          ["Restarts recorded", <span>{restarts.length}</span>],
          ["State database", <Badge tone={h.database === "ok" ? "ok" : "warn"}>{String(h.database)}</Badge>],
          ["Ledger file", <span className="muted">{String(h.ledger)}</span>],
          ["Log file", <span>{log.exists ? `${num(log.size_kb, 1)} KB` : <Val v="—" />}</span>],
          ["Lock file", <span>{h.lock_file_present ? "present" : "absent"}</span>],
        ]}
      />
      {restarts.length ? (
        <details className="section-gap">
          <summary className="faint">Restart times ({restarts.length})</summary>
          <ul className="list mono" style={{ fontSize: "var(--fs-meta)" }}>
            {restarts.slice(0, 20).map((r) => (
              <li key={r}>{utc(r)}</li>
            ))}
          </ul>
        </details>
      ) : null}
    </Panel>
  );
}

export default function Health() {
  const q = useHealth();
  return (
    <div className="page stack">
      <PageHead crumbs="System" title="System Health" lede="What the bots' own logs say about uptime and failures. Process-level metrics are not collected yet." actions={<Fetching q={q} />} />
      <DataState q={q} rows={8}>
        {(d) => {
          const modes = Object.entries(d.modes);
          const gaps = modes.filter(([, h]) => (h.candles_last_24h as number) < (h.expected_candles_24h as number));
          return (
            <>
              {gaps.length ? (
                <Callout tone="warn" title="Missed candles.">
                  {gaps.map(([m, h]) => `${m}: ${h.candles_last_24h} of ${h.expected_candles_24h}`).join("; ")} 15-minute candles were logged in the last 24 hours. Likely causes: the PC sleeping, app restarts or step failures. Each gap is time the bot was not watching the market.
                </Callout>
              ) : null}
              <div className="grid cols-2">
                {modes.map(([m, h]) => (
                  <ModeHealth key={m} name={m} h={h} />
                ))}
              </div>
              <div className="grid cols-2">
                <Panel title="Connections" flush>
                  <Table
                    caption="External connections"
                    rows={[
                      { name: "Binance public market data", role: "signal candles", state: "used (no account, no keys)" },
                      { name: "Delta Exchange India", role: "execution venue", state: "not connected" },
                      { name: "Alerting (Telegram)", role: "notifications", state: "not verified here" },
                    ]}
                    cols={[
                      { key: "name", label: "Service" },
                      { key: "role", label: "Role" },
                      { key: "state", label: "State", render: (r) => <Badge tone={r.state.startsWith("used") ? "ok" : "warn"}>{r.state}</Badge> },
                    ]}
                  />
                </Panel>
                <Panel title="Not collected">
                  <ul className="list">
                    {(d.not_collected ?? []).map((x) => (
                      <li key={x}>{x}</li>
                    ))}
                  </ul>
                  <p className="faint section-gap">Shown as missing rather than estimated. Observed {utc(d.observed_utc as string)} · heartbeat stale threshold {minutes(modes[0]?.[1].heartbeat.threshold_min)}.</p>
                </Panel>
              </div>
            </>
          );
        }}
      </DataState>
    </div>
  );
}
