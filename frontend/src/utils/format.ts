// Formatting. Every function returns "—" for missing data so "not available" never looks like zero.
export const NA = "—";

export const isNum = (v: unknown): v is number => typeof v === "number" && Number.isFinite(v);

export function usd(v: unknown, digits = 2): string {
  if (!isNum(v)) return NA;
  const sign = v < 0 ? "-" : "";
  return `${sign}$${Math.abs(v).toLocaleString("en-US", { minimumFractionDigits: digits, maximumFractionDigits: digits })}`;
}

export function inr(v: unknown): string {
  if (!isNum(v)) return NA;
  const sign = v < 0 ? "-" : "";
  return `${sign}₹${Math.round(Math.abs(v)).toLocaleString("en-IN")}`;
}

export function num(v: unknown, digits = 2): string {
  if (!isNum(v)) return NA;
  return v.toLocaleString("en-US", { minimumFractionDigits: digits, maximumFractionDigits: digits });
}

export function price(v: unknown): string {
  if (!isNum(v)) return NA;
  const a = Math.abs(v);
  return num(v, a >= 1000 ? 2 : a >= 1 ? 3 : 6);
}

/** pct(1.234) -> "+1.23%". Input is already in percent units. */
export function pct(v: unknown, digits = 2, signed = true): string {
  if (!isNum(v)) return NA;
  const s = signed && v > 0 ? "+" : "";
  return `${s}${v.toFixed(digits)}%`;
}

/** frac(0.005) -> "0.50%". Input is a fraction. */
export function frac(v: unknown, digits = 2): string {
  return isNum(v) ? `${(v * 100).toFixed(digits)}%` : NA;
}

export function qty(v: unknown): string {
  if (!isNum(v)) return NA;
  return v.toLocaleString("en-US", { maximumFractionDigits: 8 });
}

export function dir(v: unknown): "up" | "down" | "" {
  return isNum(v) ? (v > 0 ? "up" : v < 0 ? "down" : "") : "";
}

export function utc(iso: unknown, withDate = true): string {
  if (typeof iso !== "string" || !iso) return NA;
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return NA;
  const s = d.toISOString();
  return withDate ? `${s.slice(0, 10)} ${s.slice(11, 16)} UTC` : `${s.slice(11, 16)} UTC`;
}

export function ago(iso: unknown, now = Date.now()): string {
  if (typeof iso !== "string" || !iso) return NA;
  const t = new Date(iso).getTime();
  if (Number.isNaN(t)) return NA;
  const m = Math.round((now - t) / 60000);
  if (m < 1) return "just now";
  if (m < 60) return `${m} min ago`;
  const h = Math.floor(m / 60);
  if (h < 48) return `${h} h ${m % 60} min ago`;
  return `${Math.floor(h / 24)} d ago`;
}

export function minutes(v: unknown): string {
  if (!isNum(v)) return NA;
  if (v < 60) return `${Math.round(v)} min`;
  return `${Math.floor(v / 60)} h ${Math.round(v % 60)} min`;
}

/** Generic cell formatter for pass-through tables. */
export function cell(v: unknown): string {
  if (v === null || v === undefined || v === "") return NA;
  if (typeof v === "boolean") return v ? "yes" : "no";
  if (isNum(v)) return Math.abs(v) >= 1000 ? num(v, 2) : String(+v.toFixed(6));
  return String(v);
}

export function label(key: string): string {
  return key.replace(/_/g, " ").replace(/\b(usd|inr|pct|utc|atr|ks)\b/gi, (m) => m.toUpperCase());
}
