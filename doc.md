# TradeXV2 – Widget-First Quant Workspace Architecture Review & Redesign

## Objective

Review the current frontend architecture and redesign TradeXV2 as a widget-based quant workspace platform.

Do NOT design a traditional multi-page trading application.

Avoid:

```text
Many Pages

Many Routes

Deep Navigation Trees

Feature-Specific Screens

Tightly Coupled Dashboards
```

Instead design a platform similar to:

```text
Bloomberg Launchpad

Grafana

Datadog

Dexter

Notion

TradingView Multi-Layout
```

where the primary building block is:

```text
Widget
```

not:

```text
Page
```

---

# Core Principle

A user should be able to build their own workspace using reusable widgets.

Examples:

```text
Scanner Widget

Chart Widget

Option Chain Widget

OI Widget

Market Breadth Widget

Replay Widget

Strategy Widget

Positions Widget

PnL Widget

Risk Widget
```

without requiring a dedicated page.

---

# Review Existing Frontend

Analyze:

```text
Current Pages

Routes

Layouts

State Management

Component Hierarchy
```

Determine:

```text
Which screens should become widgets?

Which pages can be removed?

Which navigation structures are unnecessary?
```

---

# Target Architecture

Instead of:

```text
Scanner Page

Options Page

Research Page

Replay Page
```

Design:

```text
Workspace
    ↓
Widgets
```

Example:

```text
Research Workspace

├── Chart Widget
├── Scanner Widget
├── Relative Strength Widget
├── Market Breadth Widget
└── Watchlist Widget
```

---

# Widget Model

Every widget should support:

```text
Independent State

Independent Refresh

Independent Data Source

Independent Layout

Independent Persistence
```

---

# Widget Contract

Example:

```typescript
interface Widget {
    id: string
    type: string

    config: WidgetConfig

    refresh(): void

    render(): ReactNode
}
```

---

# Workspace Model

Example:

```text
Workspace

└── Widgets
```

User can:

```text
Add Widget

Remove Widget

Resize Widget

Move Widget

Save Layout

Share Layout
```

---

# Initial Widget Library

## Market Widgets

```text
Watchlist

Quotes

Market Breadth

Top Gainers

Top Losers

Market Status
```

---

## Scanner Widgets

```text
Scanner Results

Top Candidates

Scanner Rankings

Scanner Reasons
```

---

## Analytics Widgets

```text
Relative Strength

Volume Analysis

OI Analysis

PCR

Max Pain

Volatility
```

---

## Chart Widgets

```text
Candlestick

Volume Profile

Indicators

Multi-Timeframe
```

---

## Strategy Widgets

```text
Strategy Signals

Strategy Health

Trade History

Performance
```

---

## Replay Widgets

```text
Replay Player

Replay Timeline

Replay Orders

Replay Signals
```

---

## Portfolio Widgets

```text
PnL

Positions

Exposure

Allocation
```

---

## Risk Widgets

```text
Drawdown

Daily Risk

Open Risk

Exposure
```

---

# Workspace Types

Instead of pages.

Create workspace templates.

---

## Research Workspace

```text
Chart

Scanner

Breadth

Volume

RS
```

---

## Scanner Workspace

```text
Scanner Results

Ranking

Candidates

Charts
```

---

## Options Workspace

```text
Option Chain

PCR

OI

Greeks

Max Pain
```

---

## Replay Workspace

```text
Replay

Signals

Trades

Charts
```

---

## Live Trading Workspace

```text
Positions

Orders

PnL

Risk

Signals
```

---

# Backend Integration

Widgets should consume:

```text
REST

WebSocket

DuckDB Queries

Analytics APIs
```

through a common data layer.

Widgets must not contain business logic.

---

# Widget Registry

Support:

```typescript
registerWidget(
    widget
)
```

Adding a new widget should not require:

```text
New Route

New Page

Navigation Changes
```

---

# Layout Engine

Support:

```text
Drag & Drop

Resize

Dock

Tabs

Multi-Monitor

Persist Layouts
```

similar to Bloomberg Launchpad.

---

# State Management

Review current frontend state.

Determine:

```text
Global State

Workspace State

Widget State
```

boundaries.

Prevent unnecessary coupling.

---

# Development Productivity

Measure:

```text
How many files are required to add a widget?

How many files are required to add a workspace?

How many files are required to add a data source?
```

Goal:

```text
New Widget

< 1 Day
```

---

# Deliverables

1. Current Frontend Assessment
2. Widget-First Architecture
3. Workspace Architecture
4. Widget Contracts
5. Widget Registry Design
6. Layout Engine Design
7. State Management Plan
8. Migration Plan
9. Workspace Templates
10. Initial Widget Library
11. Frontend Simplification Recommendations
12. End-to-End Development Roadmap

---

# Most Important Questions

1. Can we replace most pages with widgets?
2. Can users build custom workspaces?
3. Can new features be delivered as widgets?
4. Can frontend complexity be reduced significantly?
5. Can scanner, replay, options, analytics, and trading all share the same widget architecture?
6. What would be deleted from the current UI?
7. What would be simplified?
8. What is the fastest path to a Bloomberg-style quant workspace platform?

---

## Status Update — 2026-06-15

The original spec above is from 2026-06-12. The system has been
brought to production-ready state through 13 remediation commits:

- **OMS wire-up** — the central OMS at `brokers/common/oms/` is now
  the canonical risk gate on the live CLI path. RiskManager is wired
  with real `gateway.funds().available_balance` as capital.
- **HTTP observability** — BrokerService now exposes /healthz, /readyz,
  /metrics on port 8765.
- **Dead-code elimination** — 9 deprecated files deleted
  (~`models.py`, `enums.py`, `connection.py`, `mappers.py`,
  `data_contracts.py`, `facade.py`, `broker.py`, `schemas.py`).
  Canonical types live in `brokers/common/core/domain.py`.

Future frontend work should target the `/api/v1/` routes described in
this spec. The Python backend already implements every endpoint here via
the broker gateway + OMS layer.
