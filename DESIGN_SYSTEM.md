# Design system

All visual values live in `frontend/src/styles/tokens.css`. Components use semantic tokens only, never raw hex.

## Principles

1. **Dense but legible.** A trading terminal, not a marketing page: 13 px body, 32 px rows, tabular monospace numbers.
2. **Colour is never the only signal.** Every status has a text label (`alive`, `HALTED`, `REJECTED`); bull/bear values carry a sign.
3. **Missing looks missing.** "—" in muted sans-serif, with "not available" for screen readers. A real zero renders as `0`.
4. **Simulated is labelled.** Paper/shadow pages carry a SIMULATED banner; historical results carry their risk-settings label.

## Typography

| Token | Size | Use |
|---|---|---|
| `--fs-wordmark` | 18 px | Product name |
| `--fs-title` | 20 px / 600 | Page title (one h1 per page) |
| `--fs-section` | 14 px / 600 | Panel titles (h2) |
| `--fs-body`, `--fs-nav` | 13 px | Body, navigation |
| `--fs-table` | 12.5 px | Table cells |
| `--fs-metric-lg` / `--fs-metric` | 26 / 16 px mono | Key figures |
| `--fs-meta` | 11.5 px | Labels, sources, timestamps |

Fonts: Inter (UI), IBM Plex Mono (numbers, timestamps, identifiers), self-hosted.

## Spacing, size, motion

* Spacing scale: 4, 8, 12, 16, 20, 24, 32, 40 px (`--sp-1` ... `--sp-8`).
* Controls: button and input 32 px (40 px under 600 px wide for touch), table row 32 px, topbar 48 px, sidebar 208 px (52 px collapsed).
* Radius 4 / 6 px. Motion 100 / 160 ms; `prefers-reduced-motion` sets both to 0 and stops the skeleton shimmer.

## Colour tokens and measured contrast (WCAG 2.2)

Ratios computed from the token values (script in the QA report). AA needs 4.5:1 for text, 3:1 for UI boundaries and graphics.

### Dark (default)

| Foreground | on bg `#090b0e` | on panel `#11151a` | on elevated | on hover |
|---|---:|---:|---:|---:|
| `--c-text` #e6edf3 | 16.67 | 15.51 | 14.49 | 13.24 |
| `--c-text-2` #9ca6b5 | 8.01 | 7.45 | 6.96 | 6.36 |
| `--c-text-3` #8a95a3 (raised from the brief's #788392) | 6.48 | 6.03 | 5.63 | 5.15 |
| `--c-accent-text` | 7.68 | 7.14 | 6.67 | 6.10 |
| `--c-bull-text` | 8.98 | 8.35 | 7.80 | 7.13 |
| `--c-bear-text` | 7.13 | 6.63 | 6.20 | 5.66 |
| `--c-warn-text` | 11.97 | 11.13 | 10.40 | 9.50 |

Badges (text on tinted background over panel): ok 7.15, bad 5.87, warn 8.99, info 7.25, accent 6.07, neutral 6.35.
Control borders `--c-border-strong` #647080: 3.64 on panel, 3.40 on elevated (was #343d49 at 1.67: failed, fixed).
White on `--c-accent` #2a67e6: 5.02 (was #3b82f6 at 3.68: failed, fixed). Focus ring vs bg: 7.68.

### Light

| Foreground | on bg `#f5f7fa` | on panel `#ffffff` | on hover |
|---|---:|---:|---:|
| `--c-text` | 16.81 | 18.05 | 15.35 |
| `--c-text-2` | 8.67 | 9.31 | 7.92 |
| `--c-text-3` | 5.88 | 6.31 | 5.36 |
| `--c-accent-text` | 6.24 | 6.70 | 5.70 |
| `--c-bull-text` | 5.48 | 5.89 | 5.01 |
| `--c-bear-text` | 6.10 | 6.55 | 5.57 |
| `--c-warn-text` | 6.38 | 6.85 | 5.83 |

Badges: ok 5.18, bad 5.79, warn 6.01, info 5.28, accent 5.82. Control borders #7b8593: 3.74 on panel, 3.30 on sidebar (was #c1c9d4 at 1.67: fixed). White on accent 5.17. Focus ring 4.82.

Panel borders (`--c-border`) are decorative separators, not control boundaries, and stay subtle.

## Components (`src/components/ui`)

| Component | Purpose | Rules |
|---|---|---|
| `Panel` | Titled section | h2 title, optional meta and actions; `flush` for tables. |
| `Strip` + `Metric` | Key-figure row | Label, mono value, sub-line; optional keyboard-reachable tooltip. |
| `Val` | Any value that may be missing | "—" + sr-only "not available". |
| `Badge`, `Status` | Labels, states | `Status` adds a dot; always with text. |
| `Callout` | info / warn / bad notices | `bad` uses `role="alert"`. |
| `DataState` | Loading / error / stale wrapper | Skeleton, error + Retry, "showing last good data". |
| `Table` | Data grids | Caption, `scope="col"`, numeric columns right-aligned mono, scrolls inside its own region, empty state instead of an empty grid. |
| `KV` | Label/value lists | `dl` semantics. |
| `Meter` | 0-100 bars | Two scales: limit used (higher = worse) and `progress` (higher = better); `role="meter"` with value. |
| `Seg` | Segmented choice | Buttons with `aria-pressed`. |
| `ModeBanner` | SIMULATED notice | On every paper/shadow page. |
| `CandleChart`, `LineChart` | Charts | Colours from tokens, rebuilt on theme change; forming candle labelled; nulls are gaps. |

## Layout breakpoints

* > 1280 px: sidebar + main/side grids (side column 340 px).
* ≤ 1280: side column 300 px. ≤ 1100: side column stacks; 3-column grids become 2.
* ≤ 860: sidebar becomes an off-canvas drawer (scrim, Escape closes, closes on navigation); all grids single-column.
* ≤ 600: metric strip 2-up, 40 px touch targets, wordmark text hidden, "LIVE DISABLED" shortened to "LIVE OFF" so it stays visible.
