import { describe, expect, it } from "vitest";
import { NA, ago, cell, frac, inr, minutes, pct, price, usd, utc } from "../src/utils/format";

describe("missing data is never shown as zero", () => {
  const missing = [null, undefined, NaN, Infinity, "", "12"];
  it.each([usd, inr, pct, frac, price, minutes])("%o returns the em dash for missing input", (f) => {
    for (const v of missing) expect(f(v as never)).toBe(NA);
  });
  it("cell treats null/undefined/empty as missing but keeps a real zero", () => {
    expect(cell(null)).toBe(NA);
    expect(cell(undefined)).toBe(NA);
    expect(cell("")).toBe(NA);
    expect(cell(0)).toBe("0");
  });
  it("a real zero stays zero", () => {
    expect(usd(0)).toBe("$0.00");
    expect(pct(0)).toBe("0.00%");
  });
});

describe("formatting", () => {
  it("signs and units", () => {
    expect(usd(-4.5)).toBe("-$4.50");
    expect(pct(1.234)).toBe("+1.23%");
    expect(pct(-2)).toBe("-2.00%");
    expect(frac(0.005)).toBe("0.50%");
    expect(inr(100000)).toBe("₹1,00,000");
  });
  it("price precision follows magnitude", () => {
    expect(price(58604.64)).toBe("58,604.64");
    expect(price(1.5)).toBe("1.500");
  });
  it("times are UTC and relative", () => {
    expect(utc("2026-11-25T17:00:11+00:00")).toBe("2026-11-25 17:00 UTC");
    expect(utc("garbage")).toBe(NA);
    const now = Date.parse("2026-11-25T18:00:00Z");
    expect(ago("2026-11-25T17:48:00Z", now)).toBe("12 min ago");
    expect(ago("2026-11-25T15:30:00Z", now)).toBe("2 h 30 min ago");
    expect(minutes(125)).toBe("2 h 5 min");
  });
});
