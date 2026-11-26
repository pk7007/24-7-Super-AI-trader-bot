// Response shapes of bot/api (schema 1.0). `null` always means "not available", never zero.
// Shapes are loose (index signatures) where the backend passes report files through unchanged.

export type Num = number | null;
export type Cell = string | number | boolean | null;
export type Row = Record<string, Cell>;

export interface Heartbeat {
  status: "alive" | "stale" | "unknown";
  last_candle_logged_utc?: string | null;
  age_min?: Num;
  threshold_min?: number;
  last_decisions?: Record<string, string>;
  last_no_data?: boolean;
  [k: string]: unknown;
}

export interface Switch {
  period?: string | null;
  start_equity?: Num;
  limit_pct?: Num;
  drawdown_pct?: Num;
  utilization_pct?: Num;
  halted?: boolean | null;
  [k: string]: unknown;
}

export interface ModeOverview {
  mode: string;
  simulated?: boolean;
  heartbeat: Heartbeat;
  equity: { value: Num; currency?: string; basis?: string; start_equity?: Num; availability: string; [k: string]: unknown };
  realized_pnl: Num;
  fill_count?: Num;
  open_positions: Num;
  open_risk_usd?: Num;
  kill_switches: Record<string, Switch>;
  entries_halted: boolean | null;
  [k: string]: unknown;
}

export interface Overview {
  modes: Record<string, ModeOverview>;
  readiness: {
    score: Num;
    classification: string | null;
    generated_utc: string | null;
    deployment_state: string;
    live_trading_allowed: boolean;
    blockers: string[];
  };
  live_trading: string;
}

export interface Markets {
  rows: Row[];
  [k: string]: unknown;
}

export interface Bar {
  t: number;
  o: number;
  h: number;
  l: number;
  c: number;
  v: number;
  closed?: boolean;
}
export interface Candles {
  availability: string;
  source: string;
  bars: Bar[];
  symbol?: string;
  signal_pair?: string;
  execution_instrument?: string;
  timeframe?: string;
  last_closed_utc?: string | null;
  data_age_min?: Num;
  error?: string;
  [k: string]: unknown;
}

export interface Rows {
  availability?: string;
  rows: Row[];
  source?: string;
  note?: string;
  simulated?: boolean;
  [k: string]: unknown;
}

export interface SignalRow {
  logged_utc: string;
  candle_label_utc?: string;
  equity: Num;
  held: string;
  decisions: Record<string, string>;
  no_data?: boolean;
  [k: string]: unknown;
}
export interface Signals {
  rows: SignalRow[];
  source: string;
  note: string;
}

export interface Risk {
  effective: Record<string, Cell>;
  policy_ceiling: Record<string, Cell>;
  discrepancies: string[];
  round_trip_cost_pct?: Num;
  protections: { name: string; status: string; verified_by?: string; [k: string]: unknown }[];
  modes: Record<string, Record<string, Switch>>;
  [k: string]: unknown;
}

export interface Metrics {
  return_pct?: Num;
  max_drawdown_pct?: Num;
  profit_factor?: Num;
  trades?: Num;
  win_rate_pct?: Num;
  [k: string]: unknown;
}
export interface MonteCarlo {
  p_loss?: Num;
  median_ret_pct?: Num;
  p5_ret_pct?: Num;
  p95_dd_pct?: Num;
  [k: string]: unknown;
}
export interface StrategyRow {
  id: string;
  label: string;
  status: string;
  evidence_tag?: string | null;
  evidence_policy?: string;
  metrics?: Metrics | null;
  monte_carlo?: MonteCarlo | null;
  subperiod_returns_pct?: Num[] | null;
  rejected_because?: string[] | null;
  [k: string]: unknown;
}
export interface Strategies {
  rows: StrategyRow[];
  [k: string]: unknown;
}

export interface Candidate {
  full?: Metrics;
  subperiod_returns_pct?: Num[];
  param_variant_returns_pct?: Num[];
  monte_carlo?: MonteCarlo;
  promote?: boolean;
  rejected_because?: string[];
  [k: string]: unknown;
}
export interface LabReport {
  tag: string;
  window?: string;
  market?: string | null;
  taker_fee?: Num;
  classification: string;
  candidates: Record<string, Candidate>;
  generated_utc?: string;
  [k: string]: unknown;
}
export interface Backtests {
  lab_reports: LabReport[];
  historical_equity: {
    availability: string;
    points?: { t: string; equity: number }[];
    drawdown?: { t: string; drawdown_pct: Num }[];
    metrics?: Record<string, unknown> | null;
    classification: string;
    [k: string]: unknown;
  };
}

export interface Readiness {
  availability?: string;
  report: Record<string, unknown> & {
    overall_score?: number;
    classification?: string;
    generated_utc?: string;
    domains?: Record<string, { weight?: number; earned?: number; score?: number; missing?: string[]; [k: string]: unknown }>;
    mandatory_blockers?: string[];
    live_trading_allowed?: boolean;
  };
  thresholds: Record<string, number>;
  weights: Record<string, number>;
  states: string[];
  anytime_states?: string[];
  live_states?: string[];
  current_state: string;
  [k: string]: unknown;
}

export interface Feasibility {
  availability?: string;
  rows: Row[];
  [k: string]: unknown;
}

export interface HealthMode {
  heartbeat: Heartbeat;
  [k: string]: unknown;
}
export interface Health {
  modes: Record<string, HealthMode>;
  not_collected?: string[];
  [k: string]: unknown;
}

export interface EventRow {
  ts_utc: string | null;
  level: string;
  logger?: string;
  message: string;
  [k: string]: unknown;
}
export interface Events {
  rows: EventRow[];
  source: string;
}
