// Page-level building blocks shared by several pages.
import { useSearchParams } from "react-router-dom";
import type { Switch } from "../types/api";
import type { Mode } from "../services/api";
import { Badge, Meter, Seg, Table, Val, type Tone } from "../components/ui";
import { pct } from "../utils/format";

export function decisionTone(d: string | undefined): Tone {
  if (d === "BUY") return "ok";
  if (d === "SELL") return "bad";
  if (!d) return "warn";
  return "";
}

export function Decision({ d }: { d: string | undefined }) {
  return <Badge tone={decisionTone(d)}>{d ?? "no data"}</Badge>;
}

/** Mode selector kept in the URL (?mode=shadow) so views can be linked and survive a reload. */
export function useModeParam(): [Mode, (m: Mode) => void] {
  const [sp, setSp] = useSearchParams();
  const m: Mode = sp.get("mode") === "shadow" ? "shadow" : "paper";
  return [
    m,
    (v) => {
      const n = new URLSearchParams(sp);
      n.set("mode", v);
      setSp(n, { replace: true });
    },
  ];
}

export function ModeSeg({ mode, set }: { mode: Mode; set: (m: Mode) => void }) {
  return (
    <Seg
      label="Trading mode"
      value={mode}
      onChange={set}
      options={[
        { v: "paper", label: "Paper" },
        { v: "shadow", label: "Shadow" },
      ]}
    />
  );
}

type KSRow = Switch & { name: string };

export function KillSwitchTable({ ks }: { ks: Record<string, Switch> | undefined }) {
  const rows: KSRow[] = ["daily", "weekly", "monthly"].map((n) => ({ name: n, ...(ks?.[n] ?? {}) }));
  return (
    <Table<KSRow>
      caption="Loss limits (kill switches)"
      rows={rows}
      cols={[
        { key: "name", label: "Limit", render: (r) => <span style={{ textTransform: "capitalize" }}>{r.name}</span> },
        { key: "period", label: "Period", render: (r) => <span className="mono">{r.period ?? "—"}</span> },
        { key: "limit_pct", label: "Max loss", num: true, render: (r) => <Val v={pct(r.limit_pct, 1, false)} /> },
        { key: "drawdown_pct", label: "Drawdown", num: true, render: (r) => <Val v={pct(r.drawdown_pct, 2)} tone={(r.drawdown_pct ?? 0) < 0 ? "down" : ""} /> },
        { key: "utilization_pct", label: "Used", render: (r) => <div style={{ width: 90 }}><Meter value={r.utilization_pct} label={`${r.name} loss limit used`} /></div> },
        {
          key: "halted",
          label: "State",
          render: (r) =>
            r.halted === true ? <Badge tone="bad">HALTED</Badge> : r.halted === false ? <Badge tone="ok">armed</Badge> : <Badge tone="warn">unknown</Badge>,
        },
      ]}
    />
  );
}
