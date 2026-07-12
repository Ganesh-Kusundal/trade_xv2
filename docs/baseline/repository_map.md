# D0.1 — Repository Map

> Generated: 2026-07-12 | Source: `find`, `wc`, `lint-imports` on `Trade_XV2`

## Summary

| Metric | Value |
|---|---|
| Total `.py` files | **1,072** |
| Total LOC (all `.py` files) | **153,149** |
| Top-level packages under `src/` | 12 (`analytics`, `application`, `brokers`, `config`, `datalake`, `domain`, `infrastructure`, `interface`, `market_data`, `runtime`, `runtime-dev`, `tradex`) |

---

## 1. Directory Tree — File Counts & LOC per Subdirectory

### Top-Level Packages

| Package | Files | LOC |
|---|---:|---:|
| `brokers` | 305 | 41,512 |
| `interface` | 157 | 23,750 |
| `domain` | 205 | 22,547 |
| `infrastructure` | 120 | 17,579 |
| `analytics` | 97 | 17,039 |
| `application` | 86 | 15,490 |
| `datalake` | 57 | 9,474 |
| `config` | 14 | 2,618 |
| `runtime` | 24 | 1,965 |
| `tradex` | 5 | 1,031 |
| `market_data` | 2 | 144 |
| **Total** | **1,072** | **153,149** |

### `src/brokers/` — 305 files, 41,512 LOC

| Subdirectory | Files | LOC |
|---|---:|---:|
| `brokers/dhan/` | 11 | 3,020 |
| `brokers/dhan/api/` | 5 | 1,422 |
| `brokers/dhan/auth/` | 8 | 798 |
| `brokers/dhan/config/` | 6 | 1,225 |
| `brokers/dhan/data/` | 13 | 2,942 |
| `brokers/dhan/execution/` | 10 | 2,036 |
| `brokers/dhan/extensions/` | 6 | 483 |
| `brokers/dhan/identity/` | 5 | 1,083 |
| `brokers/dhan/instruments/` | 2 | 219 |
| `brokers/dhan/portfolio/` | 5 | 610 |
| `brokers/dhan/resilience/` | 6 | 681 |
| `brokers/dhan/streaming/` | 5 | 1,420 |
| `brokers/dhan/websocket/` | 9 | 2,733 |
| `brokers/upstox/` | 12 | 2,042 |
| `brokers/upstox/adapters/` | 9 | 1,775 |
| `brokers/upstox/auth/` | 17 | 3,374 |
| `brokers/upstox/capabilities/` | 7 | 321 |
| `brokers/upstox/extensions/` | 3 | 149 |
| `brokers/upstox/fundamentals/` | 3 | 55 |
| `brokers/upstox/instruments/` | 7 | 981 |
| `brokers/upstox/ipo/` | 3 | 40 |
| `brokers/upstox/kill_switch/` | 3 | 41 |
| `brokers/upstox/mappers/` | 7 | 967 |
| `brokers/upstox/market_data/` | 18 | 1,130 |
| `brokers/upstox/market_intelligence/` | 4 | 260 |
| `brokers/upstox/mutual_funds/` | 3 | 46 |
| `brokers/upstox/news/` | 3 | 77 |
| `brokers/upstox/orders/` | 11 | 909 |
| `brokers/upstox/payments/` | 3 | 58 |
| `brokers/upstox/reconciliation/` | 2 | 189 |
| `brokers/upstox/static_ip/` | 3 | 41 |
| `brokers/upstox/websocket/` | 8 | 1,516 |
| `brokers/upstox/websocket/proto/` | 3 | 132 |
| `brokers/paper/` | 9 | 1,612 |
| `brokers/common/` | 12 | 795 |
| `brokers/common/api/` | 2 | 155 |
| `brokers/common/auth/` | 2 | 47 |
| `brokers/common/contracts/` | 4 | 407 |
| `brokers/common/instruments/` | 4 | 275 |
| `brokers/common/oms/` | 2 | 195 |
| `brokers/common/usecases/` | 6 | 160 |
| `brokers/certification/` | 7 | 1,054 |
| `brokers/cli/` | 5 | 1,420 |
| `brokers/diagnostics/` | 6 | 575 |
| `brokers/events/` | 1 | 17 |
| `brokers/exceptions/` | 1 | 32 |
| `brokers/extensions/` | 2 | 39 |
| `brokers/mcp/` | 3 | 289 |
| `brokers/notebooks/` | 1 | 121 |
| `brokers/runtime/` | 9 | 348 |
| `brokers/services/` | 2 | 761 |
| `brokers/session/` | 4 | 340 |

### `src/domain/` — 205 files, 22,547 LOC

| Subdirectory | Files | LOC |
|---|---:|---:|
| `domain/` (root) | 31 | 3,940 |
| `domain/instruments/` | 15 | 2,836 |
| `domain/extensions/` | 13 | 1,214 |
| `domain/ports/` | 28 | 1,672 |
| `domain/entities/` | 10 | 1,376 |
| `domain/capability_manifest/` | 4 | 1,180 |
| `domain/events/` | 4 | 1,072 |
| `domain/candles/` | 3 | 987 |
| `domain/options/` | 7 | 986 |
| `domain/indicators/` | 9 | 802 |
| `domain/orders/` | 6 | 831 |
| `domain/constants/` | 9 | 668 |
| `domain/models/` | 5 | 471 |
| `domain/value_objects/` | 6 | 481 |
| `domain/analytics/` | 3 | 424 |
| `domain/capabilities/` | 4 | 419 |
| `domain/primitives/` | 2 | 401 |
| `domain/policies/` | 2 | 398 |
| `domain/specifications/` | 4 | 293 |
| `domain/risk/` | 3 | 289 |
| `domain/portfolio/` | 4 | 307 |
| `domain/services/` | 6 | 318 |
| `domain/executions/` | 3 | 239 |
| `domain/aggregates/` | 4 | 202 |
| `domain/market/` | 5 | 155 |
| `domain/futures/` | 2 | 152 |
| `domain/providers/` | 2 | 151 |
| `domain/quotes/` | 2 | 69 |
| `domain/sessions/` | 2 | 66 |
| `domain/scanners/` | 2 | 57 |
| `domain/repositories/` | 3 | 57 |
| `domain/backtest/` | 2 | 34 |

### `src/analytics/` — 97 files, 17,039 LOC

| Subdirectory | Files | LOC |
|---|---:|---:|
| `analytics/` (root) | 3 | 1,387 |
| `analytics/replay/` | 5 | 2,433 |
| `analytics/views/` | 12 | 2,206 |
| `analytics/scanner/` | 7 | 2,139 |
| `analytics/sector/` | 6 | 1,333 |
| `analytics/backtest/` | 7 | 1,296 |
| `analytics/paper/` | 3 | 1,183 |
| `analytics/strategy/` | 6 | 840 |
| `analytics/pipeline/` | 4 | 664 |
| `analytics/options/` | 2 | 523 |
| `analytics/core/` | 5 | 586 |
| `analytics/scanner/rules/` | 4 | 342 |
| `analytics/indicators/` | 4 | 347 |
| `analytics/stocks/` | 3 | 321 |
| `analytics/walk_forward/` | 2 | 232 |
| `analytics/orderflow/` | 2 | 189 |
| `analytics/volatility/` | 2 | 156 |
| `analytics/ranking/` | 2 | 159 |
| `analytics/market_breadth/` | 2 | 142 |
| `analytics/features/` | 3 | 137 |
| `analytics/futures/` | 2 | 128 |
| `analytics/volume_profile/` | 2 | 93 |
| `analytics/strategy/builtins/` | 2 | 33 |
| `analytics/probability/` | 2 | 63 |
| `analytics/scoring/` | 1 | 17 |
| `analytics/visualizations/` | 2 | 44 |
| `analytics/reports/` | 2 | 46 |

### `src/application/` — 86 files, 15,490 LOC

| Subdirectory | Files | LOC |
|---|---:|---:|
| `application/` (root) | 3 | 323 |
| `application/oms/` | 28 | 4,509 |
| `application/oms/_internal/` | 8 | 1,966 |
| `application/services/` | 7 | 1,828 |
| `application/composer/` | 7 | 1,806 |
| `application/streaming/` | 6 | 1,422 |
| `application/trading/` | 5 | 977 |
| `application/data/` | 2 | 846 |
| `application/execution/` | 9 | 696 |
| `application/scheduling/` | 2 | 509 |
| `application/portfolio/` | 3 | 394 |
| `application/strategy_engine/` | 2 | 106 |
| `application/options/` | 2 | 85 |
| `application/oms/reconciliation/` | 2 | 23 |

### `src/infrastructure/` — 120 files, 17,579 LOC

| Subdirectory | Files | LOC |
|---|---:|---:|
| `infrastructure/` (root) | 23 | 3,412 |
| `infrastructure/observability/` | 9 | 2,623 |
| `infrastructure/event_bus/` | 8 | 1,707 |
| `infrastructure/auth/` | 14 | 1,438 |
| `infrastructure/idempotency/` | 7 | 1,624 |
| `infrastructure/resilience/` | 9 | 1,418 |
| `infrastructure/gateway/` | 5 | 590 |
| `infrastructure/connection/` | 4 | 452 |
| `infrastructure/persistence/` | 3 | 445 |
| `infrastructure/adapters/` | 4 | 376 |
| `infrastructure/lifecycle/` | 2 | 360 |
| `infrastructure/pool/` | 2 | 335 |
| `infrastructure/io/` | 4 | 301 |
| `infrastructure/security/` | 4 | 659 |
| `infrastructure/metrics/` | 4 | 668 |
| `infrastructure/mappers/` | 2 | 121 |
| `infrastructure/config/` | 3 | 158 |
| `infrastructure/providers/` | 1 | 12 |
| `infrastructure/providers/broker/` | 2 | 249 |
| `infrastructure/providers/composite/` | 2 | 181 |
| `infrastructure/providers/csv/` | 2 | 214 |
| `infrastructure/providers/dataframe/` | 2 | 158 |
| `infrastructure/db/` | 2 | 33 |
| `infrastructure/time/` | 2 | 45 |

### `src/interface/` — 157 files, 23,750 LOC

| Subdirectory | Files | LOC |
|---|---:|---:|
| `interface/` (root) | 1 | 1 |
| `interface/agent/` | 7 | 1,084 |
| `interface/api/` | 11 | 2,519 |
| `interface/api/routers/` | 16 | 3,488 |
| `interface/api/routers/live/` | 11 | 922 |
| `interface/api/v2/` | 2 | 191 |
| `interface/api/ws/` | 5 | 828 |
| `interface/ui/` | 3 | 608 |
| `interface/ui/commands/` | 50 | 7,826 |
| `interface/ui/commands/doctor/` | 4 | 705 |
| `interface/ui/commands/doctor/strategies/` | 13 | 1,044 |
| `interface/ui/commands/market_data/` | 1 | 19 |
| `interface/ui/commands/orders/` | 1 | 7 |
| `interface/ui/diagnostics/` | 1 | 71 |
| `interface/ui/load_testing/` | 1 | 128 |
| `interface/ui/services/` | 17 | 2,906 |
| `interface/ui/tests/` | 2 | 4 |
| `interface/ui/utils/` | 4 | 395 |
| `interface/ui/views/` | 1 | 75 |
| `interface/ui/widgets/` | 6 | 929 |

### `src/datalake/` — 57 files, 9,474 LOC

| Subdirectory | Files | LOC |
|---|---:|---:|
| `datalake/` (root) | 4 | 827 |
| `datalake/analytics/` | 8 | 1,972 |
| `datalake/core/` | 13 | 1,809 |
| `datalake/quality/` | 6 | 1,294 |
| `datalake/research/` | 9 | 1,092 |
| `datalake/ingestion/` | 6 | 1,009 |
| `datalake/storage/` | 5 | 1,010 |
| `datalake/adapters/` | 2 | 171 |
| `datalake/mcp/` | 4 | 290 |

### `src/config/` — 14 files, 2,618 LOC

| Subdirectory | Files | LOC |
|---|---:|---:|
| `config/` (root) | 8 | 2,226 |
| `config/profiles/` | 6 | 392 |

### `src/runtime/` — 24 files, 1,965 LOC

| Subdirectory | Files | LOC |
|---|---:|---:|
| `runtime/` (root) | 16 | 1,452 |
| `runtime/commands/` | 4 | 343 |
| `runtime/queries/` | 4 | 170 |

### `src/tradex/` — 5 files, 1,031 LOC

| Subdirectory | Files | LOC |
|---|---:|---:|
| `tradex/` (root) | 3 | 762 |
| `tradex/runtime/` | 2 | 269 |

### `src/market_data/` — 2 files, 144 LOC

---

## 2. Top 30 Largest Files by LOC

| Rank | File | LOC |
|---:|---|---:|
| 1 | `src/analytics/replay/engine.py` | 1,125 |
| 2 | `src/domain/events/types.py` | 1,008 |
| 3 | `src/domain/capability_manifest/catalog.py` | 905 |
| 4 | `src/domain/instruments/instrument.py` | 819 |
| 5 | `src/application/oms/context.py` | 809 |
| 6 | `src/domain/universe.py` | 808 |
| 7 | `src/application/trading/trading_orchestrator.py` | 807 |
| 8 | `src/domain/candles/historical.py` | 789 |
| 9 | `src/analytics/precompute_features.py` | 753 |
| 10 | `src/brokers/dhan/data/depth_feed_base.py` | 721 |
| 11 | `src/application/data/historical_coordinator.py` | 703 |
| 12 | `src/brokers/services/core.py` | 683 |
| 13 | `src/analytics/paper/engine.py` | 679 |
| 14 | `src/interface/api/schemas.py` | 678 |
| 15 | `src/application/oms/_internal/risk_manager.py` | 678 |
| 16 | `src/analytics/replay/orchestrator.py` | 670 |
| 17 | `src/brokers/upstox/auth/token_manager.py` | 650 |
| 18 | `src/brokers/dhan/api/http_client.py` | 631 |
| 19 | `src/tradex/session.py` | 621 |
| 20 | `src/analytics/facade.py` | 617 |
| 21 | `src/infrastructure/observability/alerting.py` | 598 |
| 22 | `src/brokers/dhan/streaming/connection.py` | 590 |
| 23 | `src/infrastructure/event_bus/event_bus.py` | 587 |
| 24 | `src/brokers/paper/paper_gateway.py` | 586 |
| 25 | `src/brokers/upstox/websocket/market_data_v3.py` | 565 |
| 26 | `src/brokers/cli/broker.py` | 550 |
| 27 | `src/interface/ui/commands/market.py` | 545 |
| 28 | `src/brokers/dhan/identity/identity.py` | 545 |
| 29 | `src/analytics/scanner/scanner_queries.py` | 544 |
| 30 | `src/domain/options/option_chain.py` | 536 |

---

## 3. Dead Code Candidates

### 3.1 Empty Files (0 LOC)

| File |
|---|
| `src/domain/backtest/__init__.py` |
| `src/domain/candles/__init__.py` |
| `src/domain/executions/__init__.py` |
| `src/domain/orders/__init__.py` |

These are empty `__init__.py` files — standard Python package markers, **not dead code**.

### 3.2 Import-Only Re-Export Shims (thin wrappers, ~1–9 LOC)

These files contain only a docstring + `from X import *`. They exist as backward-compatibility re-exports or convenience surfaces.

**Backward-compat re-exports (implementation in `_internal/`):**

| File | LOC | Re-exports from |
|---|---:|---|
| `src/application/oms/order_audit_logger.py` | 2 | `application.oms._internal.order_audit_logger` |
| `src/application/oms/order_position_updater.py` | 2 | `application.oms._internal.order_position_updater` |
| `src/application/oms/order_state_validator.py` | 2 | `application.oms._internal.order_state_validator` |

**Backward-compat re-exports (domain → analytics):**

| File | LOC | Re-exports from |
|---|---:|---|
| `src/analytics/indicators/halftrend.py` | 2 | `domain.indicators.halftrend` |
| `src/analytics/indicators/market_structure.py` | 2 | `domain.indicators.market_structure` |

**Test re-export:**

| File | LOC | Re-exports from |
|---|---:|---|
| `src/interface/ui/tests/endpoint_manifest.py` | 3 | `tests.component.ui.endpoint_manifest` |

**Package convenience re-exports (`__init__.py` with single re-export):**

| File | LOC | Notes |
|---|---:|---|
| `src/brokers/upstox/reconciliation/__init__.py` | 3 | Upstox client/adapter pattern |
| `src/brokers/upstox/fundamentals/__init__.py` | 3 | `" "` |
| `src/brokers/upstox/payments/__init__.py` | 3 | `" "` |
| `src/brokers/upstox/ipo/__init__.py` | 3 | `" "` |
| `src/brokers/upstox/market_data/__init__.py` | 3 | `" "` |
| `src/brokers/upstox/market_intelligence/__init__.py` | 3 | `" "` |
| `src/brokers/upstox/mutual_funds/__init__.py` | 3 | `" "` |
| `src/brokers/upstox/news/__init__.py` | 3 | `" "` |
| `src/brokers/upstox/kill_switch/__init__.py` | 3 | `" "` |
| `src/brokers/upstox/static_ip/__init__.py` | 3 | `" "` |
| `src/brokers/upstox/mappers/__init__.py` | 3 | `" "` |
| `src/brokers/upstox/orders/__init__.py` | 3 | `" "` |

**Multi-re-export aggregation packages:**

| File | LOC | Notes |
|---|---:|---|
| `src/datalake/ingestion/__init__.py` | 7 | Re-exports 5 submodules |
| `src/datalake/quality/__init__.py` | 9 | Re-exports 7 submodules |
| `src/datalake/mcp/__init__.py` | 6 | Re-exports 4 submodules |
| `src/datalake/storage/__init__.py` | 4 | Re-exports 2 submodules |
| `src/domain/indicators/__init__.py` | 8 | Re-exports 6 submodules |
| `src/analytics/scanner/rules/__init__.py` | 5 | Re-exports 3 submodules |

### 3.3 Empty `__init__.py` Filler Files (1 LOC — just `from __future__`)

Several `__init__.py` files contain only a `from __future__ import annotations` line with no other content. These are essentially empty package markers that don't re-export anything.

### 3.4 Notable Directories with No Python Code

| Path | Contents |
|---|---|
| `src/runtime-dev/instruments/` | Contains only `.csv` instrument files (~76 MB), no `.py` files |

### 3.5 Potential Dead Code Concerns

- **`src/brokers/events/__init__.py`** (17 LOC) — Re-exports all of `domain.events`. The canonical path is `domain.events`; this is a convenience surface that adds coupling.
- **`src/analytics/scoring/__init__.py`** (17 LOC) — Re-exports `analytics.probability` and `analytics.ranking` with `try/except ImportError`. These are already separate packages; the aggregation wrapper may be vestigial.
- **`src/infrastructure/providers/__init__.py`** (12 LOC) — Docstring-only, no imports. Subpackages (`broker/`, `csv/`, `composite/`, `dataframe/`) contain real implementations.
- **`src/brokers/diagnostics/schema.py`** — Not examined; schema modules in diagnostic packages can sometimes be unused if the reporting format changed.

---

## 4. File Count & LOC Summary

| Metric | Value |
|---|---|
| `.py` files under `src/` | **1,072** |
| Total LOC | **153,149** |
| Files > 500 LOC | **~30** |
| Files < 5 LOC (thin shims/stubs) | **~24** |
| Empty `.py` files | **4** (all standard `__init__.py`) |
| Largest single file | `analytics/replay/engine.py` (1,125 LOC) |
| Largest package by LOC | `brokers/` (41,512 LOC across 305 files) |
| Largest package by files | `brokers/` (305 files) |
