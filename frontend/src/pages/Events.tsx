import { useDeferredValue, useState } from "react";
import { useEvents } from "../services/api";
import { Badge, DataState, Fetching, PageHead, Panel, Seg, Table, type Tone } from "../components/ui";
import { ModeSeg, useModeParam } from "./shared";
import type { EventRow } from "../types/api";
import { utc } from "../utils/format";

const levelTone = (l: string): Tone => (l === "ERROR" || l === "CRITICAL" ? "bad" : l === "WARNING" ? "warn" : "");

export default function Events() {
  const [mode, setMode] = useModeParam();
  const [level, setLevel] = useState<"all" | "warn">("all");
  const [text, setText] = useState("");
  const needle = useDeferredValue(text.trim().toLowerCase());
  const q = useEvents(mode);
  return (
    <div className="page stack">
      <PageHead
        crumbs="System"
        title="Event Log"
        lede="The bot's own log, newest first. Times are converted from the PC's local clock to UTC."
        actions={
          <>
            <ModeSeg mode={mode} set={setMode} />
            <Seg
              label="Level"
              value={level}
              onChange={setLevel}
              options={[
                { v: "all", label: "All" },
                { v: "warn", label: "Warnings+" },
              ]}
            />
            <label className="sr-only" htmlFor="ev-search">
              Search events
            </label>
            <input id="ev-search" className="input" type="search" placeholder="Search messages" value={text} onChange={(e) => setText(e.target.value)} />
            <Fetching q={q} />
          </>
        }
      />
      <Panel title="Events" meta={q.data?.data.source} flush>
        <DataState q={q} rows={8}>
          {(d) => {
            const rows = d.rows.filter((r) => (level === "all" || r.level !== "INFO") && (!needle || r.message.toLowerCase().includes(needle)));
            return (
              <Table<EventRow>
                caption="Bot event log"
                rows={rows}
                maxHeight={680}
                empty="No events match."
                cols={[
                  { key: "ts_utc", label: "Time (UTC)", render: (r) => <span className="mono">{utc(r.ts_utc)}</span> },
                  { key: "level", label: "Level", render: (r) => <Badge tone={levelTone(r.level)}>{r.level}</Badge> },
                  { key: "logger", label: "Source", render: (r) => <span className="mono faint">{r.logger ?? "—"}</span> },
                  { key: "message", label: "Message", wrap: true, render: (r) => <span className="mono" style={{ fontSize: "var(--fs-meta)" }}>{r.message}</span> },
                ]}
              />
            );
          }}
        </DataState>
      </Panel>
    </div>
  );
}
