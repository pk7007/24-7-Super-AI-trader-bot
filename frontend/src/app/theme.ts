// Theme state (dark default). Persisted in localStorage "atl.theme"; applied as <html data-theme>.
import { createContext, useContext } from "react";

export type Theme = "dark" | "light";
export const THEME_KEY = "atl.theme";

export function initialTheme(): Theme {
  try {
    const t = localStorage.getItem(THEME_KEY);
    if (t === "dark" || t === "light") return t;
  } catch {
    /* storage blocked: fall back to default */
  }
  return "dark";
}

export function applyTheme(t: Theme) {
  document.documentElement.dataset.theme = t;
  try {
    localStorage.setItem(THEME_KEY, t);
  } catch {
    /* ignore */
  }
}

export const ThemeCtx = createContext<{ theme: Theme; setTheme: (t: Theme) => void }>({ theme: "dark", setTheme: () => {} });
export const useTheme = () => useContext(ThemeCtx).theme;
export const useSetTheme = () => useContext(ThemeCtx).setTheme;
