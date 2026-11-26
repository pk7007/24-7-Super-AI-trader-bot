// Typed client for the read-only observational API (bot/api). GET only.
import { useQuery, type UseQueryResult } from "@tanstack/react-query";
import type * as T from "../types/api";

export interface Envelope<D> {
  schema_version: string;
  observed_utc: string;
  data: D;
}

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

export async function getJSON<D>(path: string, signal?: AbortSignal): Promise<Envelope<D>> {
  let res: Response;
  try {
    res = await fetch(path, { signal, headers: { Accept: "application/json" }, credentials: "omit" });
  } catch (e) {
    if ((e as Error)?.name === "AbortError") throw e;
    throw new ApiError(0, "API unreachable. Start it with: python -m bot.api");
  }
  if (!res.ok) throw new ApiError(res.status, `API error ${res.status}`);
  const body = (await res.json()) as Envelope<D>;
  if (body.schema_version !== "1.0") throw new ApiError(res.status, `Unsupported API schema ${body.schema_version}`);
  return body;
}

// Poll intervals match how often the data really changes: the engine writes once per 15-minute candle,
// so polling faster than every 30-60 s only burns requests.
const MIN = 60_000;
function q<D>(key: unknown[], path: string, refetchMs: number | false): UseQueryResult<Envelope<D>, ApiError> {
  return useQuery<Envelope<D>, ApiError>({
    queryKey: key,
    queryFn: ({ signal }) => getJSON<D>(path, signal),
    refetchInterval: refetchMs,
    staleTime: typeof refetchMs === "number" ? refetchMs / 2 : 5 * MIN,
  });
}

export type Mode = "paper" | "shadow";
export type Sym = "BTC" | "ETH" | "SOL";

export const useOverview = () => q<T.Overview>(["overview"], "/api/v1/overview", 30_000);
export const useMarkets = () => q<T.Markets>(["markets"], "/api/v1/markets", MIN);
export const useCandles = (s: Sym, source: "live" | "cached") =>
  q<T.Candles>(["candles", s, source], `/api/v1/candles?symbol=${s}&limit=500&source=${source}`, source === "live" ? MIN : false);
export const usePositions = (m: Mode) => q<T.Rows>(["positions", m], `/api/v1/positions?mode=${m}`, 30_000);
export const useFills = (m: Mode) => q<T.Rows>(["fills", m], `/api/v1/fills?mode=${m}`, MIN);
export const useSignals = (m: Mode) => q<T.Signals>(["signals", m], `/api/v1/signals?mode=${m}&limit=400`, MIN);
export const useIntents = () => q<T.Rows>(["intents"], "/api/v1/intents", MIN);
export const useRisk = () => q<T.Risk>(["risk"], "/api/v1/risk", MIN);
export const useStrategies = () => q<T.Strategies>(["strategies"], "/api/v1/strategies", false);
export const useBacktests = () => q<T.Backtests>(["backtests"], "/api/v1/backtests", false);
export const useReadiness = () => q<T.Readiness>(["readiness"], "/api/v1/readiness", 5 * MIN);
export const useFeasibility = () => q<T.Feasibility>(["feasibility"], "/api/v1/feasibility", false);
export const useLedger = (m: Mode) => q<T.Rows>(["ledger", m], `/api/v1/ledger?mode=${m}`, MIN);
export const useHealth = () => q<T.Health>(["health"], "/api/v1/health", 30_000);
export const useEvents = (m: Mode) => q<T.Events>(["events", m], `/api/v1/events?mode=${m}&limit=300`, MIN);
