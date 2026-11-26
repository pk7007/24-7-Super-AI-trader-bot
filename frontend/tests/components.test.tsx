import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import type { UseQueryResult } from "@tanstack/react-query";
import { DataState, Metric, Table, Val } from "../src/components/ui";
import { ApiError, getJSON, type Envelope } from "../src/services/api";

afterEach(cleanup);

function fake<D>(p: Partial<UseQueryResult<Envelope<D>, ApiError>>) {
  return { isPending: false, isError: false, isFetching: false, refetch: vi.fn(), ...p } as unknown as UseQueryResult<Envelope<D>, ApiError>;
}

describe("Val / Metric", () => {
  it("missing values say 'not available' to screen readers", () => {
    render(<Val v="—" />);
    expect(screen.getByTitle("Not available").textContent).toContain("not available");
  });
  it("Metric renders its label and value", () => {
    render(<Metric label="Equity" value="$113.60" />);
    expect(screen.getByText("Equity")).toBeTruthy();
    expect(screen.getByText("$113.60")).toBeTruthy();
  });
});

describe("DataState", () => {
  it("shows a loading state", () => {
    render(<DataState q={fake<number>({ isPending: true })}>{() => <p>data</p>}</DataState>);
    expect(screen.getByText("Loading")).toBeTruthy();
    expect(screen.queryByText("data")).toBeNull();
  });
  it("shows an error with a retry button when there is no data", () => {
    render(<DataState q={fake<number>({ isError: true, error: new ApiError(0, "API unreachable") })}>{() => <p>data</p>}</DataState>);
    expect(screen.getByRole("alert").textContent).toContain("API unreachable");
    expect(screen.getByRole("button", { name: /retry/i })).toBeTruthy();
  });
  it("keeps last good data visible but warns when a refresh fails", () => {
    const data = { schema_version: "1.0", observed_utc: new Date().toISOString(), data: 7 };
    render(<DataState q={fake<number>({ isError: true, error: new ApiError(500, "API error 500"), data })}>{(d) => <p>value {d}</p>}</DataState>);
    expect(screen.getByText("value 7")).toBeTruthy();
    expect(screen.getByText(/Showing last good data/)).toBeTruthy();
  });
});

describe("Table", () => {
  it("renders an empty-state message instead of an empty grid", () => {
    render(<Table caption="Fills" rows={[]} cols={[{ key: "a", label: "A" }]} empty="No fills yet." />);
    expect(screen.getByText("No fills yet.")).toBeTruthy();
    expect(screen.queryByRole("table")).toBeNull();
  });
  it("renders missing cells as not available, zero as zero", () => {
    render(<Table caption="T" rows={[{ a: null, b: 0 }]} cols={[{ key: "a", label: "A" }, { key: "b", label: "B" }]} />);
    expect(screen.getByTitle("Not available")).toBeTruthy();
    expect(screen.getByText("0")).toBeTruthy();
  });
});

describe("api client", () => {
  it("rejects an unknown schema version", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify({ schema_version: "2.0", observed_utc: "", data: 1 }), { status: 200 })));
    await expect(getJSON("/api/v1/overview")).rejects.toThrow(/schema/);
    vi.unstubAllGlobals();
  });
  it("turns a network failure into a readable message", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => { throw new TypeError("Failed to fetch"); }));
    await expect(getJSON("/api/v1/overview")).rejects.toThrow(/python -m bot.api/);
    vi.unstubAllGlobals();
  });
  it("only ever issues GET requests", async () => {
    const f = vi.fn(async () => new Response(JSON.stringify({ schema_version: "1.0", observed_utc: "", data: 1 }), { status: 200 }));
    vi.stubGlobal("fetch", f);
    await getJSON("/api/v1/risk");
    const init = (f.mock.calls[0] as unknown[])[1] as RequestInit;
    expect(init.method ?? "GET").toBe("GET");
    expect(init.body).toBeUndefined();
    vi.unstubAllGlobals();
  });
});
