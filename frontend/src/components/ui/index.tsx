// UI primitives. Every visual value comes from tokens.css via app.css classes.
import type { ReactNode } from "react";
import type { UseQueryResult } from "@tanstack/react-query";
import { AlertTriangle, CircleSlash, Info, Loader2, OctagonAlert, RefreshCw } from "lucide-react";
import type { ApiError, Envelope } from "../../services/api";
import { NA, ago, cell, isNum } from "../../utils/format";

export type Tone = "ok" | "bad" | "warn" | "info" | "accent" | "outline" | "";

export function Panel(props: {
  title: ReactNode;
  meta?: ReactNode;
  actions?: ReactNode;
  flush?: boolean;
  children: ReactNode;
  className?: string;
  id?: string;
}) {
  const hid = props.id ? `${props.id}-h` : undefined;
  return (
    <section className={`panel ${props.className ?? ""}`} aria-labelledby={hid} id={props.id}>
      <div className="panel-head">
        <div className="row" style={{ minWidth: 0, flexWrap: "nowrap" }}>
          <h2 id={hid}>{props.title}</h2>
          {props.meta ? <span className="meta">{props.meta}</span> : null}
        </div>
        {props.actions ? <div className="row">{props.actions}</div> : null}
      </div>
      <div className={`panel-body ${props.flush ? "flush" : ""}`}>{props.children}</div>
    </section>
  );
}

/** A value that may be missing. Missing renders as an em dash with an accessible "not available" label. */
export function Val({ v, tone }: { v: string; tone?: "up" | "down" | "" }) {
  if (v === NA)
    return (
      <span className="na" title="Not available">
        {NA}
        <span className="sr-only"> not available</span>
      </span>
    );
  return <span className={tone || undefined}>{v}</span>;
}

export function Metric(props: { label: ReactNode; value: string; sub?: ReactNode; tone?: "up" | "down" | ""; lg?: boolean; tip?: string }) {
  return (
    <div className="metric">
      <div className="metric-label">
        {props.label}
        {props.tip ? (
          <span tabIndex={0} data-tip={props.tip} aria-label={props.tip} className="faint" style={{ display: "inline-flex" }}>
            <Info size={12} aria-hidden />
          </span>
        ) : null}
      </div>
      <div className={`metric-value ${props.lg ? "lg" : ""}`}>
        <Val v={props.value} tone={props.tone} />
      </div>
      {props.sub ? <div className="metric-sub">{props.sub}</div> : null}
    </div>
  );
}

export function Strip({ children, label }: { children: ReactNode; label: string }) {
  return (
    <div className="strip" role="group" aria-label={label}>
      {children}
    </div>
  );
}

export function Badge({ tone = "", children, title }: { tone?: Tone; children: ReactNode; title?: string }) {
  return (
    <span className={`badge ${tone}`} title={title}>
      {children}
    </span>
  );
}

/** Status with a dot plus a text label, so colour is never the only signal. */
export function Status({ tone, children }: { tone: Tone; children: ReactNode }) {
  return (
    <Badge tone={tone}>
      <span className="dot" aria-hidden />
      {children}
    </Badge>
  );
}

export function heartbeatTone(s: string | undefined): Tone {
  return s === "alive" ? "ok" : s === "stale" ? "bad" : "warn";
}

export function Callout({ tone = "info", children, title }: { tone?: "info" | "warn" | "bad"; children: ReactNode; title?: ReactNode }) {
  const Icon = tone === "bad" ? OctagonAlert : tone === "warn" ? AlertTriangle : Info;
  return (
    <div className={`callout ${tone}`} role={tone === "bad" ? "alert" : "note"}>
      <Icon aria-hidden />
      <div>
        {title ? <strong>{title} </strong> : null}
        {children}
      </div>
    </div>
  );
}

export function Empty({ children }: { children: ReactNode }) {
  return (
    <div className="state" role="status">
      <CircleSlash aria-hidden />
      <div>{children}</div>
    </div>
  );
}

export function Skeleton({ rows = 3 }: { rows?: number }) {
  return (
    <div className="stack" style={{ padding: "var(--sp-4)" }} aria-busy="true" aria-live="polite">
      <span className="sr-only">Loading</span>
      {Array.from({ length: rows }, (_, i) => (
        <div key={i} className="skeleton" style={{ width: `${90 - i * 15}%` }} />
      ))}
    </div>
  );
}

/** Renders loading, error and success states of a query. When a refetch fails after an earlier success,
 *  the last data stays visible with an explicit warning instead of silently looking current. */
export function DataState<D>({ q, children, rows }: { q: UseQueryResult<Envelope<D>, ApiError>; children: (d: D, observed: string) => ReactNode; rows?: number }) {
  if (q.isPending) return <Skeleton rows={rows} />;
  if (q.isError && !q.data)
    return (
      <div className="state error" role="alert">
        <OctagonAlert aria-hidden />
        <div className="stack" style={{ gap: 8 }}>
          <div>{q.error?.message ?? "Request failed"}</div>
          <div>
            <button className="btn" type="button" onClick={() => q.refetch()}>
              <RefreshCw aria-hidden /> Retry
            </button>
          </div>
        </div>
      </div>
    );
  const env = q.data!;
  return (
    <>
      {q.isError ? (
        <div style={{ padding: "var(--sp-2) var(--sp-3) 0" }}>
          <Callout tone="warn" title="Showing last good data.">
            Refresh failed ({q.error?.message}); observed {ago(env.observed_utc)}.
          </Callout>
        </div>
      ) : null}
      {children(env.data, env.observed_utc)}
    </>
  );
}

export function Fetching({ q }: { q: { isFetching: boolean } }) {
  return q.isFetching ? <Loader2 size={14} className="faint spin" aria-label="Refreshing" /> : null;
}

export interface Col<R> {
  key: string;
  label: ReactNode;
  num?: boolean;
  wrap?: boolean;
  render?: (r: R) => ReactNode;
}

export function Table<R extends object>(props: { cols: Col<R>[]; rows: R[]; caption: string; empty?: ReactNode; maxHeight?: number }) {
  if (!props.rows.length) return <Empty>{props.empty ?? "No rows."}</Empty>;
  return (
    <div className="table-wrap" style={props.maxHeight ? { maxHeight: props.maxHeight } : undefined} tabIndex={0} role="region" aria-label={props.caption}>
      <table className="data">
        <caption className="sr-only">{props.caption}</caption>
        <thead>
          <tr>
            {props.cols.map((c) => (
              <th key={c.key} scope="col" className={c.num ? "r" : undefined}>
                {c.label}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {props.rows.map((r, i) => (
            <tr key={i}>
              {props.cols.map((c) => (
                <td key={c.key} className={[c.num ? "r" : "", c.wrap ? "wrap" : ""].join(" ").trim() || undefined}>
                  {c.render ? c.render(r) : <Val v={cell((r as Record<string, unknown>)[c.key])} />}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function KV({ items }: { items: [ReactNode, ReactNode][] }) {
  return (
    <dl className="kv">
      {items.map(([k, v], i) => (
        <div key={i} style={{ display: "contents" }}>
          <dt>{k}</dt>
          <dd>{v}</dd>
        </div>
      ))}
    </dl>
  );
}

/** 0-100 bar. Default reads as a limit being used up (higher = worse); `progress` reads as a score (higher = better). */
export function Meter({ value, label, progress = false }: { value: number | null | undefined; label: string; progress?: boolean }) {
  if (!isNum(value)) return <Val v={NA} />;
  const v = Math.max(0, Math.min(100, value));
  const tone = progress ? (v >= 80 ? "ok" : v >= 40 ? "warn" : "bad") : v >= 100 ? "bad" : v >= 60 ? "warn" : "ok";
  return (
    <div className={`bar ${tone}`} role="meter" aria-valuemin={0} aria-valuemax={100} aria-valuenow={Math.round(v)} aria-label={label} title={progress ? `${v.toFixed(0)}% of maximum` : `${v.toFixed(0)}% used`}>
      <span style={{ width: `${Math.max(v, 1)}%` }} />
    </div>
  );
}

export function Seg<T extends string>({ value, options, onChange, label }: { value: T; options: { v: T; label: ReactNode }[]; onChange: (v: T) => void; label: string }) {
  return (
    <div className="seg" role="group" aria-label={label}>
      {options.map((o) => (
        <button key={o.v} type="button" aria-pressed={o.v === value} onClick={() => onChange(o.v)}>
          {o.label}
        </button>
      ))}
    </div>
  );
}

export function ModeBanner({ mode }: { mode: "paper" | "shadow" }) {
  return (
    <div className="mode-banner" role="note">
      <Badge tone="info">SIMULATED</Badge>
      {mode === "paper" ? (
        <span>
          <strong>Paper mode.</strong> Orders fill against a simulated broker. No real money, no exchange account.
        </span>
      ) : (
        <span>
          <strong>Shadow mode.</strong> Records the orders the bot would send; nothing is sent to an exchange.
        </span>
      )}
    </div>
  );
}

export function PageHead({ crumbs, title, lede, actions }: { crumbs: string; title: string; lede?: ReactNode; actions?: ReactNode }) {
  return (
    <div className="page-head">
      <div>
        <div className="crumbs">{crumbs}</div>
        <h1>{title}</h1>
        {lede ? <p className="lede">{lede}</p> : null}
      </div>
      {actions ? <div className="row">{actions}</div> : null}
    </div>
  );
}

export function Source({ children }: { children: ReactNode }) {
  return <span className="faint">Source: {children}</span>;
}
