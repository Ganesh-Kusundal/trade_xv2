# TradeXV2 — Widget-First Architecture: Analysis & Plan

## 1. Current State Analysis

### What's in the Frontend Today
- **16 feature pages** under `src/features/` (dashboard, market, research, scanner, analytics, strategies, backtest, replay, options, portfolio, positions, orders, risk, alerts, reports, settings)
- **AppShell** in `src/components/shell/` renders the active feature based on `useUIStore.workspace`
- **Each feature is a self-contained page** with its own layout, data fetch, and UI
- **Sidebar nav** hard-codes the 16 destinations as routes

### Critical Problems with Page-Based Architecture

| Problem | Impact | Severity |
|---|---|---|
| 16 monolith features, no reuse | Adding a new visualization means creating a new page + route + nav | 🔴 Critical |
| Layouts are fixed per page | User cannot move/resize/reorder anything | 🔴 Critical |
| Same data shown in 3+ places (e.g. P&L, positions, equity curve) | UI duplication, drift, maintenance burden | 🔴 Critical |
| Each feature fetches its own data | No shared data layer, no caching, no cross-feature sharing | 🟠 High |
| Sidebar is a route list, not a workspace | Cannot compose workflows from reusable building blocks | 🔴 Critical |
| Settings/persistence is per-page | No way to save "my morning routine" view | 🟠 High |
| No widget contract | Every feature invents its own layout/state pattern | 🟠 High |

### What Can Become Widgets (Mapping)

| Current Page | Becomes |
|---|---|
| Dashboard | "Default Workspace" template (4 hero KPI widgets + 6 panel widgets) |
| Market | Watchlist widget + Chart widget + Order ticket widget |
| Research | Chart widget + Studies widget + Notes widget |
| Scanner | Scanner Builder widget + Scan Results widget + Top Candidates widget |
| Analytics | 7 widgets (RS, OI, PCR, Max Pain, Breadth, Volume, Volatility) |
| Strategies | Strategy Card widget + Trades widget + Logs widget |
| Backtest | Equity Curve widget + Trade Log widget + Metrics widget |
| Replay | Replay Player widget + Replay Chart widget + Replay Trades widget |
| Options | Option Chain widget + Greeks widget + PCR/MaxPain widgets |
| Portfolio | Holdings widget + Allocation widget + PnL widget |
| Positions | Positions widget + P&L widget |
| Orders | Orders widget + Quick Order widget |
| Risk | Risk Gauge widget + Drawdown widget + Stress Test widget |
| Alerts | Alerts Feed widget + Alert Templates widget |
| Reports | Reports List widget + Performance widget |
| Settings | (Stays a page — admin/config, not trading UI) |

**Total widgets to build: ~25**
**Total workspaces: ~6 templates** (Research, Live Trading, Options, Replay, Scanner, Default)

## 2. Target Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│  Sidebar: Workspaces + Widget Gallery + Quick Tools              │
├──────────────────────────────────────────────────────────────────┤
│  Topbar: Workspace switcher + Symbol + Broker + Market Status     │
├──────────────────────────────────────────────────────────────────┤
│  Workspace Canvas (react-grid-layout)                            │
│  ┌─────────┬──────────────┬──────────────┐                       │
│  │Widget 1 │ Widget 2     │ Widget 3     │                       │
│  │(Resize, ├──────────────┼──────────────┤                       │
│  │ move,   │ Widget 4     │ Widget 5     │                       │
│  │ config) │              │              │                       │
│  └─────────┴──────────────┴──────────────┘                       │
├──────────────────────────────────────────────────────────────────┤
│  Status Bar: WS, Latency, P&L summary                            │
└──────────────────────────────────────────────────────────────────┘
```

### Widget Contract

```typescript
interface WidgetManifest<TConfig = any> {
  type: string                          // 'chart', 'watchlist', etc.
  name: string
  category: 'market' | 'scanner' | 'analytics' | 'chart' | 'strategy' | 'replay' | 'portfolio' | 'risk' | 'options'
  icon: LucideIcon
  description: string
  defaultSize: { w: number; h: number; minW: number; minH: number }
  configSchema?: ConfigField[]
  component: React.ComponentType<WidgetProps<TConfig>>
  defaultConfig: () => TConfig
}

interface WidgetInstance {
  id: string                            // uuid
  type: string                          // matches manifest.type
  config: Record<string, any>
  layout: { x: number; y: number; w: number; h: number }
  data?: any                            // cached widget data
}
```

### Workspace Contract

```typescript
interface Workspace {
  id: string
  name: string
  icon?: string
  widgets: WidgetInstance[]
  createdAt: number
  updatedAt: number
  isTemplate?: boolean
  builtIn?: boolean                     // cannot be deleted
}
```

## 3. Implementation Plan

### Files to Create

```
src/
├── widgets/                            # NEW
│   ├── Widget.ts                       # Core types & interfaces
│   ├── registry.ts                     # WidgetRegistry singleton
│   ├── WidgetFrame.tsx                 # Chrome (title, refresh, settings, remove)
│   ├── useWidgetData.ts                # Data-fetching hook with auto-refresh
│   ├── DataLayer.ts                    # Central REST/WS/DuckDB abstraction
│   └── library/                        # The widget library
│       ├── watchlist/WatchlistWidget.tsx
│       ├── chart/ChartWidget.tsx
│       ├── scan-results/ScanResultsWidget.tsx
│       ├── scan-builder/ScanBuilderWidget.tsx
│       ├── top-candidates/TopCandidatesWidget.tsx
│       ├── relative-strength/RSHeatmapWidget.tsx
│       ├── pcr-gauge/PCRGaugeWidget.tsx
│       ├── max-pain/MaxPainWidget.tsx
│       ├── oi-heatmap/OIHeatmapWidget.tsx
│       ├── volatility/VolatilityWidget.tsx
│       ├── positions/PositionsWidget.tsx
│       ├── orders/OrdersWidget.tsx
│       ├── pnl-summary/PnLSummaryWidget.tsx
│       ├── holdings/HoldingsWidget.tsx
│       ├── quick-order/QuickOrderWidget.tsx
│       ├── market-depth/MarketDepthWidget.tsx
│       ├── risk-gauge/RiskGaugeWidget.tsx
│       ├── drawdown/DrawdownWidget.tsx
│       ├── alerts-feed/AlertsFeedWidget.tsx
│       ├── strategy-list/StrategyListWidget.tsx
│       ├── equity-curve/EquityCurveWidget.tsx
│       ├── option-chain/OptionChainWidget.tsx
│       ├── greeks/GreeksWidget.tsx
│       ├── breadth/BreadthWidget.tsx
│       └── index.ts
├── workspaces/                         # NEW
│   ├── Workspace.tsx                   # Grid container
│   ├── store.ts                        # Zustand workspace store
│   ├── templates.ts                    # Predefined templates
│   ├── WidgetGallery.tsx               # Add-widget modal
│   ├── WorkspaceHeader.tsx             # Top toolbar
│   └── index.ts
└── components/shell/
    ├── Sidebar.tsx                     # MODIFIED: workspace list + gallery
    └── ...
```

### Migration Strategy

1. **Keep current workspaces as "page-mode"** for backward compat (Settings, Reports, Alerts, Orders, Positions, Portfolio, Risk).
2. **Replace page-mode with widget-mode** for the trading/research workflows: Research, Market, Scanner, Analytics, Strategies, Backtest, Replay, Options.
3. **Add "Workspaces" as a new top-level sidebar group** with built-in templates + user-saved.
4. **Default to Workspace mode on app load.**

## 4. UX Flow

### First-time user
1. Opens app → sees **"Default Workspace"** (6 widgets pre-arranged).
2. Clicks **"+ Widget"** in toolbar → opens **Widget Gallery** → picks "Risk Gauge" → drops into grid.
3. Drags widget to new position, resizes, clicks ⚙ to configure.
4. Renames workspace: "My Morning" → Saves.
5. Opens **Workspace Switcher** in sidebar → creates new workspace from template "Live Trading" → customizes.

### Power user
- Hotkey `⌘+K` to open command palette
- Saves 5+ named workspaces for different workflows
- One workspace per monitor (multi-monitor)

## 5. State Boundaries

| State | Owner | Lifetime |
|---|---|---|
| UI prefs (sidebar collapsed, theme) | uiStore (existing) | Persistent |
| Current workspace ID | workspaceStore | Persistent |
| Workspace list (saved) | workspaceStore (localStorage) | Persistent |
| Widget instances (per workspace) | workspaceStore | Persistent |
| Widget config | workspaceStore | Persistent |
| Widget data (live quotes) | useWidgetData hook | Ephemeral (refetched) |
| Order/position state | services (mock) → replace with WS | Ephemeral |

## 6. Deliverables Checklist

- [x] Layout engine (react-grid-layout)
- [x] Widget framework (Frame, Registry, Data hook)
- [x] 15+ widgets
- [x] 6+ workspace templates
- [x] Widget Gallery (add widget modal)
- [x] Workspace store with persistence
- [x] Sidebar with workspace list
- [x] Drag/resize/add/remove/configure widgets
- [x] Save/load/duplicate/delete workspaces
- [x] Migrate current features to widgets where appropriate
- [x] Build clean
- [x] Type check clean

## 7. Risk & Mitigations

| Risk | Mitigation |
|---|---|
| react-grid-layout CSS conflicts | Use scoped imports + reset |
| Widget data fetching thrashes backend | Use DataLayer with request dedup + cache TTL |
| Layouts broken on resize | react-grid-layout handles responsive breakpoints natively |
| Performance with 20+ widgets | Memoize + virtualize if needed |
| User loses layout | Auto-save on every change to localStorage |
