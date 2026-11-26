// App shell: topbar with real system status, grouped sidebar (collapsible, off-canvas on mobile), main outlet.
import { Suspense, useEffect, useState, type ReactNode } from "react";
import { NavLink, Outlet, useLocation } from "react-router-dom";
import { Activity, Lock, Menu, Moon, PanelLeftClose, PanelLeftOpen, Sun } from "lucide-react";
import { NAV, findNav } from "./nav";
import { useOverview } from "../services/api";
import { Badge, Skeleton, Status, heartbeatTone } from "../components/ui";
import { ThemeCtx } from "./theme";
import { useContext } from "react";
import { ago, minutes } from "../utils/format";

const SIDEBAR_KEY = "atl.sidebar";

function readCollapsed(): boolean {
  try {
    return localStorage.getItem(SIDEBAR_KEY) === "collapsed";
  } catch {
    return false;
  }
}

export function TopStatus() {
  const q = useOverview();
  if (q.isPending) return <span className="status-item">Loading status…</span>;
  // A failed refresh must never leave old "alive" badges on screen: show the outage and the data's age instead.
  if (q.isError)
    return (
      <>
        <span className="status-item" role="status">
          <Status tone="bad">API offline</Status>
          {q.data ? <span className="hide-sm">last data {ago(q.data.observed_utc)}</span> : null}
        </span>
        <span className="status-item">
          <Badge tone="bad" title="No live service exists; live needs BOT_MODE=live + human approval">
            <Lock aria-hidden /> <span className="hide-xs">LIVE DISABLED</span>
            <span className="show-xs">LIVE OFF</span>
          </Badge>
        </span>
      </>
    );
  const d = q.data!.data;
  const items: ReactNode[] = [];
  for (const m of ["paper", "shadow"] as const) {
    const hb = d.modes[m]?.heartbeat;
    items.push(
      <span key={m} className="status-item" title={`Last engine candle log: ${minutes(hb?.age_min)} ago (stale after ${hb?.threshold_min ?? "?"} min)`}>
        <span className="hide-sm" style={{ textTransform: "capitalize" }}>
          {m}
        </span>
        <span className="only-mobile" aria-hidden>
          {m === "paper" ? "P" : "S"}
        </span>
        <Status tone={heartbeatTone(hb?.status)}>
          <span className="sr-only">{m} bot </span>
          {hb?.status ?? "unknown"}
        </Status>
      </span>,
    );
  }
  return (
    <>
      {items}
      <span className="status-item hide-sm">
        State <Badge tone="accent">{d.readiness.deployment_state}</Badge>
      </span>
      <span className="status-item hide-sm" title="Trading readiness score from bot/readiness.py (not frontend quality)">
        Readiness <span className="mono">{d.readiness.score ?? "—"}/100</span>
      </span>
      <span className="status-item">
        <Badge tone="bad" title={d.live_trading}>
          <Lock aria-hidden /> <span className="hide-xs">LIVE DISABLED</span>
          <span className="show-xs">LIVE OFF</span>
        </Badge>
      </span>
    </>
  );
}

export function Shell() {
  const [collapsed, setCollapsed] = useState(readCollapsed);
  const [mobileOpen, setMobileOpen] = useState(false);
  const { theme, setTheme } = useContext(ThemeCtx);
  const loc = useLocation();
  const here = findNav(loc.pathname);

  useEffect(() => {
    try {
      localStorage.setItem(SIDEBAR_KEY, collapsed ? "collapsed" : "expanded");
    } catch {
      /* ignore */
    }
  }, [collapsed]);
  useEffect(() => setMobileOpen(false), [loc.pathname]);
  useEffect(() => {
    document.title = `${here?.item.label ?? "Not found"} · AI Trade Labs`;
  }, [here]);
  useEffect(() => {
    if (!mobileOpen) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setMobileOpen(false);
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [mobileOpen]);

  return (
    <div className="shell" data-collapsed={collapsed} data-mobile-open={mobileOpen}>
      <a href="#main" className="skip-link">
        Skip to content
      </a>
      <header className="topbar">
        <button type="button" className="btn icon ghost only-mobile" aria-label="Open navigation" aria-expanded={mobileOpen} aria-controls="sidebar" onClick={() => setMobileOpen((v) => !v)}>
          <Menu aria-hidden />
        </button>
        <button type="button" className="btn icon ghost only-desktop" aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"} aria-pressed={collapsed} onClick={() => setCollapsed((v) => !v)}>
          {collapsed ? <PanelLeftOpen aria-hidden /> : <PanelLeftClose aria-hidden />}
        </button>
        <div className="wordmark">
          <span className="mark" aria-hidden>
            <Activity size={14} strokeWidth={2.5} />
          </span>
          <span className="wordmark-text">AI Trade Labs</span> <small>OBSERVATORY</small>
        </div>
        <div className="topbar-spacer" />
        <div className="topbar-status" aria-label="System status" role="group">
          <TopStatus />
        </div>
        <button type="button" className="btn icon ghost" aria-label={`Switch to ${theme === "dark" ? "light" : "dark"} theme`} onClick={() => setTheme(theme === "dark" ? "light" : "dark")}>
          {theme === "dark" ? <Sun aria-hidden /> : <Moon aria-hidden />}
        </button>
      </header>
      <nav className="sidebar" id="sidebar" aria-label="Main">
        {NAV.map((g) => (
          <div className="nav-group" key={g.label}>
            <div className="nav-group-label" aria-hidden={collapsed}>
              {g.label}
            </div>
            {g.items.map((i) => (
              <NavLink key={i.to} to={i.to} end className="nav-link" title={collapsed ? i.label : undefined}>
                <i.icon aria-hidden />
                <span className="nav-label">{i.label}</span>
              </NavLink>
            ))}
          </div>
        ))}
      </nav>
      {mobileOpen ? <div className="scrim" aria-hidden onClick={() => setMobileOpen(false)} /> : null}
      <main className="main" id="main" tabIndex={-1}>
        <Suspense fallback={<div className="page"><Skeleton rows={6} /></div>}>
          <Outlet />
        </Suspense>
      </main>
    </div>
  );
}
