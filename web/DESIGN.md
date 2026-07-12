# UI Context — TradeXV2 / TradeX Web Trading UI

> Part of the **Six-File Context System**. Defines the visual language for `web/`. The
> agent must never invent visual decisions — it reads this file. Grounded in the actual
> `web/` stack: React 18 + TypeScript + Vite, plain `styles.css` (no component library
> yet), react-router 6, Vitest. Extend tokens here as the design system matures.

## 1. Stack & Conventions

- **React 18** function components + hooks. Routing via `react-router-dom` v6.
- **No UI component library installed** — build with native elements + `web/src/styles.css`.
  Do NOT add a component library (MUI, Chakra, etc.) without explicit instruction.
- Types in `web/src/types.ts`; components in `web/src/components`; feature hooks in
  `web/src/hooks`; data access in `web/src/api` (generated client).

## 2. Color Tokens (semantic, not raw hex)

> The agent should reference these token names. Add new tokens here rather than inlining
> hex values in components.

| Token | Purpose | Suggested (adjust to actual theme) |
|---|---|---|
| `--bg-base` | App background | dark slate `#0b0e14` |
| `--bg-surface` | Panels/cards | `#121722` |
| `--bg-elevated` | Modals/overlays | `#1a2030` |
| `--text-primary` | Primary text | `#e6e9ef` |
| `--text-muted` | Secondary text | `#8b93a7` |
| `--border-subtle` | Borders/dividers | `#232a3a` |
| `--accent` | Primary action / brand | `#3b82f6` (blue) |
| `--success` | Long / profit / positive | `#22c55e` (green) |
| `--danger` | Short / loss / negative | `#ef4444` (red) |
| `--warning` | Pending / caution | `#f59e0b` (amber) |

> Trading convention: **green = long/profit, red = short/loss**. Do not swap these.

## 3. Typography

- System UI stack (no web-font dependency yet): `-apple-system, Segoe UI, Roboto, sans-serif`.
- Numerics (P&L, prices, quantities) use tabular figures / monospace for alignment.
- Scale (rem): display 1.5, title 1.25, body 1.0, caption 0.8125, micro 0.6875.

## 4. Border Radius & Spacing

- Radius scale: sm 4px, md 8px, lg 12px, pill 999px.
- Spacing scale (4px base): 1=4, 2=8, 3=12, 4=16, 6=24, 8=32.

## 5. Layout Patterns

- **App shell**: left nav / sidebar for primary surfaces (Markets, Orders, Positions,
  Portfolio, Strategy), top bar with broker/profile + connection status, main content area.
- **Data tables** (orders, positions, tradebook): sticky header, right-aligned numerics,
  row color hint by side (long/short).
- **Status indicators**: use `--success`/`--warning`/`--danger` dots for order state
  (filled/executed/pending/rejected/cancelled).
- **Modals**: centered, `--bg-elevated`, used for order confirmation and risk kill-switch.
- **Empty states**: explicit placeholder + primary action (no dead screens).

## 6. Icon Usage

- Inline SVG or a single icon source; no icon font dependency yet. Prefer semantic icons
  (buy/sell, refresh, alert) over decorative ones.

## 7. Accessibility

- Interactive elements are real buttons/inputs (keyboard reachable). Status conveyed by
  text/aria-label, not color alone. Honor `prefers-reduced-motion`.
