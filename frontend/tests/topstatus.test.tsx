import { afterEach, describe, expect, it, vi } from "vitest";
import { act, cleanup, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { TopStatus } from "../src/app/Shell";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

const overview = {
  schema_version: "1.0",
  observed_utc: new Date().toISOString(),
  data: {
    modes: {
      paper: { mode: "paper", heartbeat: { status: "alive", age_min: 3, threshold_min: 40 } },
      shadow: { mode: "shadow", heartbeat: { status: "alive", age_min: 3, threshold_min: 40 } },
    },
    readiness: { score: 43, classification: "DEVELOPMENT ONLY", generated_utc: null, deployment_state: "PAPER", live_trading_allowed: false, blockers: [] },
    live_trading: "disabled",
  },
};

function setup() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={client}>
      <TopStatus />
    </QueryClientProvider>,
  );
  return client;
}

describe("TopStatus", () => {
  it("shows both heartbeats and the live-disabled badge when the API answers", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify(overview), { status: 200 })));
    setup();
    await waitFor(() => expect(screen.getAllByText("alive")).toHaveLength(2));
    expect(screen.getByText("LIVE DISABLED")).toBeTruthy();
  });

  it("never keeps old 'alive' badges once a refresh fails", async () => {
    let up = true;
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => {
        if (!up) throw new TypeError("Failed to fetch");
        return new Response(JSON.stringify(overview), { status: 200 });
      }),
    );
    const client = setup();
    await waitFor(() => expect(screen.getAllByText("alive")).toHaveLength(2));
    up = false;
    await act(async () => {
      await client.refetchQueries({ queryKey: ["overview"] });
    });
    await waitFor(() => expect(screen.getByText("API offline")).toBeTruthy());
    expect(screen.queryByText("alive")).toBeNull();
    expect(screen.getByText("LIVE DISABLED")).toBeTruthy();
  });
});
