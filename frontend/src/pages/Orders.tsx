import { useFills, useIntents, usePositions } from "../services/api";
import { Badge, DataState, Fetching, ModeBanner, PageHead, Panel } from "../components/ui";
import { ModeSeg, useModeParam } from "./shared";
import { FillsTable, IntentsTable, PositionsTable } from "./tables";

export default function Orders() {
  const [mode, setMode] = useModeParam();
  const pos = usePositions(mode);
  const fills = useFills(mode);
  const intents = useIntents();
  return (
    <div className="page stack">
      <PageHead
        crumbs="Trading"
        title="Orders & Positions"
        lede="Positions and fills as the bot recorded them in its own database. Quantities are shown in coins; the engine's internal lot units are shown alongside."
        actions={
          <>
            <ModeSeg mode={mode} set={setMode} />
            <Fetching q={fills} />
          </>
        }
      />
      <ModeBanner mode={mode} />
      <Panel title="Open positions" meta={pos.data?.data.note as string | undefined} flush>
        <DataState q={pos}>{(d) => <PositionsTable rows={d.rows} availability={d.availability} />}</DataState>
      </Panel>
      <Panel title="Fills" meta={fills.data?.data.source} flush>
        <DataState q={fills}>{(d) => <FillsTable rows={d.rows} availability={d.availability} />}</DataState>
      </Panel>
      {mode === "shadow" ? (
        <Panel title="Order intentions" meta={intents.data?.data.source} flush>
          <DataState q={intents}>{(d) => <IntentsTable rows={d.rows} availability={d.availability} />}</DataState>
        </Panel>
      ) : null}
      <span className="faint">
        <Badge tone="outline">read-only</Badge> No order entry exists in this application by design.
      </span>
    </div>
  );
}
