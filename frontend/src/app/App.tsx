// Routes. Pages are lazy-loaded so the first screen ships only what it needs.
import { Component, lazy, type ReactNode } from "react";
import { createBrowserRouter, Link, useRouteError } from "react-router-dom";
import { Shell } from "./Shell";

const CommandCenter = lazy(() => import("../pages/CommandCenter"));
const MarketTerminal = lazy(() => import("../pages/MarketTerminal"));
const ModeWorkspace = lazy(() => import("../pages/ModeWorkspace"));
const Orders = lazy(() => import("../pages/Orders"));
const Signals = lazy(() => import("../pages/Signals"));
const StrategyLab = lazy(() => import("../pages/StrategyLab"));
const Backtesting = lazy(() => import("../pages/Backtesting"));
const Feasibility = lazy(() => import("../pages/Feasibility"));
const RiskCenter = lazy(() => import("../pages/RiskCenter"));
const Readiness = lazy(() => import("../pages/Readiness"));
const Ledger = lazy(() => import("../pages/Ledger"));
const Health = lazy(() => import("../pages/Health"));
const Events = lazy(() => import("../pages/Events"));
const SettingsPage = lazy(() => import("../pages/Settings"));

/** Catches render errors inside one page so the shell and navigation keep working. */
export class PageBoundary extends Component<{ children: ReactNode }, { err: Error | null }> {
  state = { err: null as Error | null };
  static getDerivedStateFromError(err: Error) {
    return { err };
  }
  render() {
    if (this.state.err)
      return (
        <div className="page">
          <div className="callout bad" role="alert">
            <div>
              <strong>This page failed to load.</strong> {this.state.err.message}. If the API was restarted or stopped, start it again and reload.{" "}
              <button type="button" className="btn" onClick={() => window.location.reload()}>
                Reload
              </button>
            </div>
          </div>
        </div>
      );
    return this.props.children;
  }
}

function RouteError() {
  const e = useRouteError() as Error | undefined;
  return (
    <div className="page">
      <div className="callout bad" role="alert">
        <div>
          <strong>Something went wrong.</strong> {e?.message ?? "Unknown error"}. <Link to="/">Back to Command Center</Link>
        </div>
      </div>
    </div>
  );
}

function NotFound() {
  return (
    <div className="page">
      <h1>Page not found</h1>
      <p className="lede">
        This route does not exist. <Link to="/">Go to the Command Center</Link>.
      </p>
    </div>
  );
}

const wrap = (n: ReactNode) => <PageBoundary>{n}</PageBoundary>;

export const router = createBrowserRouter([
  {
    element: <Shell />,
    errorElement: <RouteError />,
    children: [
      { path: "/", element: wrap(<CommandCenter />) },
      { path: "/market", element: wrap(<MarketTerminal />) },
      { path: "/paper", element: wrap(<ModeWorkspace mode="paper" />) },
      { path: "/shadow", element: wrap(<ModeWorkspace mode="shadow" />) },
      { path: "/orders", element: wrap(<Orders />) },
      { path: "/signals", element: wrap(<Signals />) },
      { path: "/strategies", element: wrap(<StrategyLab />) },
      { path: "/backtests", element: wrap(<Backtesting />) },
      { path: "/feasibility", element: wrap(<Feasibility />) },
      { path: "/risk", element: wrap(<RiskCenter />) },
      { path: "/readiness", element: wrap(<Readiness />) },
      { path: "/ledger", element: wrap(<Ledger />) },
      { path: "/health", element: wrap(<Health />) },
      { path: "/events", element: wrap(<Events />) },
      { path: "/settings", element: wrap(<SettingsPage />) },
      { path: "*", element: <NotFound /> },
    ],
  },
]);
