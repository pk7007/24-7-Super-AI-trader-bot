// Navigation model. Only routes with real backing data exist; see FRONTEND_ARCHITECTURE.md for omitted ones.
import {
  Activity,
  BadgeCheck,
  BookOpen,
  CandlestickChart,
  ClipboardList,
  FlaskConical,
  Gauge,
  History,
  LayoutDashboard,
  type LucideIcon,
  Radar,
  ScrollText,
  Settings,
  ShieldAlert,
  Wallet,
  Waypoints,
} from "lucide-react";

export interface NavItem {
  to: string;
  label: string;
  icon: LucideIcon;
}
export interface NavGroup {
  label: string;
  items: NavItem[];
}

export const NAV: NavGroup[] = [
  { label: "Workspace", items: [{ to: "/", label: "Command Center", icon: LayoutDashboard }] },
  {
    label: "Trading",
    items: [
      { to: "/market", label: "Market Terminal", icon: CandlestickChart },
      { to: "/paper", label: "Paper Trading", icon: Wallet },
      { to: "/shadow", label: "Shadow Trading", icon: Waypoints },
      { to: "/orders", label: "Orders & Positions", icon: ClipboardList },
      { to: "/signals", label: "Signals", icon: Radar },
    ],
  },
  {
    label: "Research",
    items: [
      { to: "/strategies", label: "Strategy Lab", icon: FlaskConical },
      { to: "/backtests", label: "Backtesting", icon: History },
      { to: "/feasibility", label: "Capital Feasibility", icon: Gauge },
    ],
  },
  {
    label: "Risk & Operations",
    items: [
      { to: "/risk", label: "Risk Management", icon: ShieldAlert },
      { to: "/readiness", label: "Live Readiness", icon: BadgeCheck },
    ],
  },
  { label: "Finance", items: [{ to: "/ledger", label: "Ledger & Tax", icon: BookOpen }] },
  {
    label: "System",
    items: [
      { to: "/health", label: "System Health", icon: Activity },
      { to: "/events", label: "Event Log", icon: ScrollText },
      { to: "/settings", label: "Settings", icon: Settings },
    ],
  },
];

export function findNav(path: string): { group: string; item: NavItem } | null {
  for (const g of NAV) for (const i of g.items) if (i.to === path) return { group: g.label, item: i };
  return null;
}
