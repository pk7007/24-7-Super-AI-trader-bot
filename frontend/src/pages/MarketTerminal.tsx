import { useMemo } from "react";
import { useSearchParams } from "react-router-dom";
import { useCandles, useFills, useMarkets, useRisk, useSignals, type Sym } from "../services/api";
import { Badge, Callout, DataState, Fetching, KV, PageHead, Panel, Seg, Source, Table, Val } from "../components/ui";
import { CandleChart, toTs, type Marker } from "../components/charts/Charts";
import { Decision } from "./shared";
import type { SignalRow } from "../types/api";
import { dir, frac, minutes, pct, price, utc } from "../utils/format";

const SYMS: Sym[] = ["BTC", "ETH", "SOL"];

export default function MarketTerminal() {
  const [sp, setSp] = useSearchParams();
  const sym: Sym = (SYMS as string[]).includes(sp.get("symbol") ?? "") ? (sp.get("symbol") as Sym) : "BTC";
  const source = sp.get("source") === "cached" ? "cached" : "live";
  const set = (k: string, v: string) => {
    const n = new URLSearchParams(sp);
    n.set(k, v);
    setSp(n, { replace: true });
  };
  const cq = useCandles(sym, source);
  const mk = useMarkets();
  const rk = useRisk();
  const fills = useFills("paper");
  const sig = useSignals("paper");

  const markers = useMemo<Marker[]>(() => {
    const rows = fills.data?.data.rows ?? [];
    return rows
      .filter((f) => String(f.symbol ?? "").startsWith(sym + "/") && typeof f.ts === "string")
      .map((f) => {
        const t = toTs(String(f.ts));
        return { t: t - (t % 900), side: String(f.side).toLowerCase() === "sell" ? "sell" : "buy", text: `paper ${String(f.side).toUpperCase()}` } as Marker;
      });
  }, [fills.data, sym]);

  const market = mk.data?.data.rows.find((r) => r.symbol === sym);

  return (
    <div className="page stack">
      <PageHead
        crumbs="Trading"
        title="Market Terminal"
        lede="The 15-minute candles the strategy reads. The bot decides only on closed candles; the forming candle is shown for context and labelled."
        actions={
          <>
            <Seg label="Symbol" value={sym} onChange={(v) => set("symbol", v)} options={SYMS.map((s) => ({ v: s, label: s }))} />
            <Seg
              label="Data source"
              value={source}
              onChange={(v) => set("source", v)}
              options={[
                { v: "live", label: "Live" },
                { v: "cached", label: "Cached" },
              ]}
            />
            <Fetching q={cq} />
          </>
        }
      />
      <div className="grid cols-main-side">
        <Panel title={`${sym}/USDT · 15m`} meta={cq.data?.data.source} flush>
          <DataState q={cq} rows={8}>
            {(d) =>
              d.bars.length ? (
                <>
                  {source === "cached" || (d.data_age_min ?? 0) > 30 ? (
                    <div style={{ padding: "var(--sp-2) var(--sp-3) 0" }}>
                      <Callout tone="warn" title={source === "cached" ? "Cached data, not live." : "Data is old."}>
                        Last closed candle {utc(d.last_closed_utc)} ({minutes(d.data_age_min)} ago).
                      </Callout>
                    </div>
                  ) : null}
                  <CandleChart bars={d.bars} markers={markers} height={460} label={`${sym} 15 minute candlestick chart, ${d.bars.length} bars, ${d.source}`} />
                  <div className="row" style={{ padding: "var(--sp-2) var(--sp-3)", justifyContent: "space-between" }}>
                    <Source>{d.source}</Source>
                    <span className="faint">
                      Last closed {utc(d.last_closed_utc)} · {d.bars.length} bars · markers = paper fills ({markers.length})
                    </span>
                  </div>
                </>
              ) : (
                <div className="state">No candles available: {d.availability}{d.error ? ` (${d.error})` : ""}.</div>
              )
            }
          </DataState>
        </Panel>
        <div className="stack">
          <Panel title="Instrument">
            {market ? (
              <KV
                items={[
                  ["Signal pair", <span>{String(market.signal_pair)}</span>],
                  ["Signal venue", <span className="faint">{String(market.signal_venue)}</span>],
                  ["Executes as", <span>{String(market.execution_instrument)}</span>],
                  ["Execution venue", <Badge tone="warn">not connected</Badge>],
                  ["Last closed candle", <Val v={price(market.last_close)} />],
                  ["24h change", <Val v={pct(market.change_24h_pct)} tone={dir(market.change_24h_pct)} />],
                  ["Paper decision", <Decision d={market.paper_decision as string | undefined} />],
                  ["Shadow decision", <Decision d={market.shadow_decision as string | undefined} />],
                ]}
              />
            ) : (
              <DataState q={mk}>{() => <Val v="—" />}</DataState>
            )}
          </Panel>
          <Panel title="Risk per trade" meta="effective config">
            <DataState q={rk}>
              {(r) => (
                <KV
                  items={[
                    ["Risk budget", <Val v={frac(r.effective.risk_per_trade as number)} />],
                    ["Stop distance", <span>{String(r.effective.stop_atr)} × ATR</span>],
                    ["Round-trip cost", <Val v={pct(r.round_trip_cost_pct, 3, false)} />],
                    ["Max positions", <span>{String(r.effective.max_positions)}</span>],
                    ["Leverage", <span>{String(r.effective.max_leverage)}×</span>],
                    ["Shorting", <span>{r.effective.allow_short ? "allowed" : "off"}</span>],
                  ]}
                />
              )}
            </DataState>
          </Panel>
        </div>
      </div>
      <Panel title={`Engine decisions · ${sym}`} meta="paper bot, newest first, one row per closed candle" flush>
        <DataState q={sig}>
          {(d) => (
            <Table<SignalRow>
              caption={`Paper engine decisions for ${sym}`}
              maxHeight={320}
              rows={d.rows.slice(0, 96)}
              empty="No engine decisions logged yet."
              cols={[
                { key: "logged_utc", label: "Logged (UTC)", render: (r) => <span className="mono">{utc(r.logged_utc)}</span> },
                { key: "candle_label_utc", label: "Candle", render: (r) => <span className="mono">{r.candle_label_utc ?? "—"}</span> },
                { key: "d", label: "Decision", render: (r) => <Decision d={r.decisions?.[sym]} /> },
                { key: "held", label: "Held", render: (r) => <span>{r.held}</span> },
                { key: "no_data", label: "Data", render: (r) => (r.no_data ? <Badge tone="warn">no data</Badge> : <Badge tone="outline">ok</Badge>) },
              ]}
            />
          )}
        </DataState>
      </Panel>
    </div>
  );
}

