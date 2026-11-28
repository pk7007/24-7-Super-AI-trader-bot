import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import StrategyLab from "../src/pages/StrategyLab";
import ModeWorkspace from "../src/pages/ModeWorkspace";

const fixture = vi.hoisted(() => ({
  strategy: { rows: [{ id: "ensemble", label: "Ensemble", status: "passed lab gate (deployment not inferred)", evidence_policy: "historical: obsolete or unrecorded simulation version", metrics: null }] },
  overview: { modes: { paper: { mode: "paper", accounting_halted: true, entries_halted: true,
    heartbeat: { status: "alive", age_min: 1 }, equity: { value: 113.6 }, realized_pnl: 0, open_positions: 0,
    kill_switches: {} } } },
}));

vi.mock("../src/services/api", () => {
  const query = (data: unknown) => ({ isPending: false, isError: false, isFetching: false,
    data: { data, schema_version: "1.0", observed_utc: "2026-11-28T12:00:00Z" } });
  return {
    useStrategies: () => query(fixture.strategy), useOverview: () => query(fixture.overview),
    usePositions: () => query({ rows: [] }), useFills: () => query({ rows: [] }),
    useSignals: () => query({ rows: [] }), useIntents: () => query({ rows: [] }),
  };
});

vi.mock("../src/components/charts/Charts", () => ({ LineChart: () => null }));
afterEach(cleanup);

describe("evidence and accounting safety", () => {
  it("labels obsolete ensemble results without claiming current-policy deployment", () => {
    render(<StrategyLab />);
    expect(screen.queryByText("Ensemble · current policy")).toBeNull();
    expect(screen.getAllByText("historical: obsolete or unrecorded simulation version").length).toBeGreaterThan(0);
    expect(screen.getByText("Ensemble · recorded evidence")).toBeTruthy();
  });

  it("shows a persistent accounting halt even while candle heartbeats are healthy", () => {
    render(<MemoryRouter><ModeWorkspace mode="paper" /></MemoryRouter>);
    expect(screen.getByRole("alert").textContent).toContain("Accounting reconciliation required");
    expect(screen.getByRole("alert").textContent).toContain("New entries are halted");
  });
});
