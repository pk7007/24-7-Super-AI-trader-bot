// Charts on TradingView lightweight-charts v5 (Apache-2.0; its attribution logo stays on as the licence asks).
// Colours are read from CSS tokens, so charts follow the theme. Used by MarketTerminal, ModeWorkspace, Backtesting.
import { useEffect, useRef, useState } from "react";
import {
  AreaSeries,
  CandlestickSeries,
  ColorType,
  HistogramSeries,
  LineSeries,
  createChart,
  createSeriesMarkers,
  type IChartApi,
  type SeriesMarker,
  type Time,
  type UTCTimestamp,
} from "lightweight-charts";
import type { Bar } from "../../types/api";
import { useTheme } from "../../app/theme";
import { price as fmtPrice } from "../../utils/format";

function token(name: string): string {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
}

function baseOptions() {
  return {
    autoSize: true,
    layout: {
      background: { type: ColorType.Solid, color: "transparent" },
      textColor: token("--chart-text"),
      fontFamily: token("--font-mono"),
      fontSize: 11,
      attributionLogo: true,
    },
    grid: { vertLines: { color: token("--chart-grid") }, horzLines: { color: token("--chart-grid") } },
    rightPriceScale: { borderColor: token("--c-border") },
    timeScale: { borderColor: token("--c-border"), timeVisible: true, secondsVisible: false },
    crosshair: { mode: 0 },
  };
}

export const toTs = (iso: string) => Math.floor(new Date(iso.replace(" ", "T")).getTime() / 1000) as UTCTimestamp;

export interface Marker {
  t: number;
  side: "buy" | "sell";
  text: string;
}

/** Candles + volume. The last bar is labelled FORMING when the API says it has not closed. */
export function CandleChart({ bars, height = 420, markers, label }: { bars: Bar[]; height?: number; markers?: Marker[]; label: string }) {
  const el = useRef<HTMLDivElement>(null);
  const theme = useTheme();
  const [hover, setHover] = useState<Bar | null>(null);
  const last = bars[bars.length - 1];

  useEffect(() => {
    if (!el.current || !bars.length) return;
    const chart: IChartApi = createChart(el.current, baseOptions());
    const up = token("--c-bull");
    const down = token("--c-bear");
    const ref = bars[bars.length - 1].c;
    const candles = chart.addSeries(CandlestickSeries, {
      upColor: up,
      downColor: down,
      borderUpColor: up,
      borderDownColor: down,
      wickUpColor: up,
      wickDownColor: down,
      priceFormat: { type: "price", precision: ref >= 1000 ? 2 : 3, minMove: ref >= 1000 ? 0.01 : 0.001 },
    });
    candles.setData(bars.map((b) => ({ time: b.t as UTCTimestamp, open: b.o, high: b.h, low: b.l, close: b.c })));
    const vol = chart.addSeries(HistogramSeries, { priceScaleId: "vol", priceFormat: { type: "volume" }, lastValueVisible: false, priceLineVisible: false });
    chart.priceScale("vol").applyOptions({ scaleMargins: { top: 0.82, bottom: 0 } });
    vol.setData(bars.map((b) => ({ time: b.t as UTCTimestamp, value: b.v, color: (b.c >= b.o ? up : down) + "55" })));
    if (markers?.length) {
      const ms: SeriesMarker<Time>[] = markers
        .slice()
        .sort((a, b) => a.t - b.t)
        .map((m) => ({
          time: m.t as UTCTimestamp,
          position: m.side === "buy" ? "belowBar" : "aboveBar",
          shape: m.side === "buy" ? "arrowUp" : "arrowDown",
          color: m.side === "buy" ? up : down,
          text: m.text,
        }));
      createSeriesMarkers(candles, ms);
    }
    chart.subscribeCrosshairMove((p) => {
      if (!p.time) return setHover(null);
      setHover(bars.find((b) => b.t === p.time) ?? null);
    });
    chart.timeScale().fitContent();
    return () => chart.remove();
  }, [bars, markers, theme]);

  const b = hover ?? last;
  return (
    <div className="chart-box" style={{ height }} role="img" aria-label={label}>
      {b ? (
        <div className="chart-legend" aria-hidden>
          <span>O {fmtPrice(b.o)}</span>
          <span>H {fmtPrice(b.h)}</span>
          <span>L {fmtPrice(b.l)}</span>
          <span className={b.c >= b.o ? "up" : "down"}>C {fmtPrice(b.c)}</span>
          {b.closed === false ? <span className="badge warn">FORMING (not used by the bot)</span> : <span className="badge outline">CLOSED</span>}
        </div>
      ) : null}
      <div ref={el} style={{ position: "absolute", inset: 0 }} />
    </div>
  );
}

export interface LinePoint {
  t: string;
  v: number | null;
}

/** Single line or area series, e.g. equity or drawdown. Null points are skipped (gaps), never drawn as zero. */
export function LineChart({ points, height = 240, area = false, tone = "line", label, suffix = "", logo = true }: { points: LinePoint[]; height?: number; area?: boolean; tone?: "line" | "bear"; label: string; suffix?: string; logo?: boolean }) {
  const el = useRef<HTMLDivElement>(null);
  const theme = useTheme();
  useEffect(() => {
    if (!el.current || !points.length) return;
    const base = baseOptions();
    // One logo per page: a second logo would duplicate its element ids. Pages that pass logo={false}
    // carry a text attribution instead, which the Apache-2.0 NOTICE also accepts.
    const chart = createChart(el.current, { ...base, layout: { ...base.layout, attributionLogo: logo }, crosshair: { mode: 1 } });
    const color = tone === "bear" ? token("--c-bear") : token("--chart-line");
    const data: { time: UTCTimestamp; value: number }[] = [];
    let prev = -Infinity;
    for (const p of points) {
      if (p.v === null || !Number.isFinite(p.v)) continue;
      const ts = toTs(p.t);
      if (ts <= prev) continue; // lightweight-charts needs strictly increasing time
      prev = ts;
      data.push({ time: ts, value: p.v });
    }
    const fmt = { type: "custom" as const, formatter: (v: number) => `${v.toFixed(2)}${suffix}` };
    const s = area
      ? chart.addSeries(AreaSeries, { lineColor: color, topColor: color + "44", bottomColor: color + "05", lineWidth: 2, priceFormat: fmt })
      : chart.addSeries(LineSeries, { color, lineWidth: 2, priceFormat: fmt });
    s.setData(data);
    chart.timeScale().fitContent();
    return () => chart.remove();
  }, [points, theme, area, tone, suffix, logo]);
  return <div ref={el} className="chart-box" style={{ height }} role="img" aria-label={label} />;
}
