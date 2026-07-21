# Architectural Audit REF Completion Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Complete all remaining refactoring tasks from the Architectural Audit Phases 3-5 (REF-2 partial, REF-3, REF-5 partial, REF-9 partial, REF-11, REF-14 partial, REF-15 partial).

**Architecture:** Each task is independent and can be worked in parallel where noted. Tasks are sequenced by dependency: REF-2/REF-3 first (enum standardization), then REF-9 (import paths), then REF-5 (model consolidation), then REF-11 (typed models), then REF-14/REF-15 (guardrails).

**Tech Stack:** Python 3.13, ruff, mypy, import-linter, pytest

## Global Constraints

- All changes must pass existing test suites (architecture, unit, integration)
- No behavior changes — pure refactoring (type replacements, import path changes)
- Backward-compat aliases preserved where they exist already
- `Side` is a `str` enum (`Side.BUY == "BUY"` is `True`) so replacements are safe
- `Exchange` is a `str` enum (`Exchange.NSE == "NSE"` is `True`) so replacements are safe
- Run `ruff check src/` and `ruff format src/` after each task
- Run affected test suites after each task

---

## Task 1: REF-2 — Replace String "BUY"/"SELL" with Side Enum in Analytics

**Files:**
- Modify: `src/analytics/simulation/signal_processor.py` (lines 192, 228)
- Modify: `src/analytics/paper/signal_processor.py` (lines 97, 118, 153)
- Modify: `src/analytics/replay/signal_processor.py` (lines 64, 83, 117)
- Modify: `src/analytics/replay/position_closer.py` (line 63)
- Modify: `src/analytics/backtest/fast_backtest.py` (lines 164, 186, 198, 225)
- Modify: `src/analytics/indicators/halftrend_backtest.py` (lines 131, 139)
- Modify: `src/analytics/replay/models.py` (lines 209, 253, 282, 336, 371)
- Modify: `src/analytics/simulation/position_closer.py` (line 33 — hook return type)
- Modify: `src/analytics/replay/position_closer.py` (line 101)
- Modify: `src/analytics/paper/position_closer.py` (lines 82, 98)

**Interfaces:**
- Consumes: `domain.enums.Side` (already available)
- Produces: All analytics modules use `Side.BUY`/`Side.SELL` instead of strings

- [ ] **Step 1: Fix simulation/signal_processor.py**

In `src/analytics/simulation/signal_processor.py`, add `from domain.enums import Side` to imports, then replace:

```python
# Line 192: side="BUY", → side=Side.BUY,
# Line 228: side="SELL", → side=Side.SELL,
```

- [ ] **Step 2: Fix paper/signal_processor.py**

In `src/analytics/paper/signal_processor.py`, add `from domain.enums import Side` to imports, then replace:

```python
# Line 97: self._commission(price * qty, "BUY") → self._commission(price * qty, Side.BUY)
# Line 118: self._commission(price * quantity, "BUY") → self._commission(price * quantity, Side.BUY)
# Line 153: self._commission(price * qty, "SELL") → self._commission(price * qty, Side.SELL)
```

- [ ] **Step 3: Fix replay/signal_processor.py**

In `src/analytics/replay/signal_processor.py`, add `from domain.enums import Side` to imports, then replace:

```python
# Line 64: self._fill_recorder.compute_commission(notional, "BUY") → ...Side.BUY)
# Line 83: self._fill_recorder.compute_commission(notional, "BUY") → ...Side.BUY)
# Line 117: self._fill_recorder.compute_commission(notional, "SELL") → ...Side.SELL)
```

- [ ] **Step 4: Fix replay/position_closer.py and paper/position_closer.py**

In `src/analytics/simulation/position_closer.py`, update the `close_side` hook type:
```python
# Line ~33: Change return type of close_side from Callable[[Any], str] to Callable[[Any], Side]
```

In `src/analytics/replay/position_closer.py`:
```python
# Line 63: self._fill_recorder.compute_commission(notional, "SELL") → ...Side.SELL)
# Line 101: close_side=lambda view: "SELL", → close_side=lambda view: Side.SELL,
```

In `src/analytics/paper/position_closer.py`:
```python
# Line 82: return "SELL" if view.side == PositionSide.LONG else "BUY" → return Side.SELL if ... else Side.BUY
# Line 98: close_side = Side.SELL if slip_side == "SELL" else Side.BUY  (already correct pattern)
```

- [ ] **Step 5: Fix backtest/fast_backtest.py**

In `src/analytics/backtest/fast_backtest.py`, add `from domain.enums import Side` to imports, then replace:

```python
# Line 164: side="BUY", → side=Side.BUY,
# Line 186: side="SELL", → side=Side.SELL,
# Line 198: exchange="NSE", → exchange=DEFAULT_EXCHANGE,  (also REF-3)
# Line 225: exchange="NSE", → exchange=DEFAULT_EXCHANGE,  (also REF-3)
```

- [ ] **Step 6: Fix indicators/halftrend_backtest.py**

In `src/analytics/indicators/halftrend_backtest.py`, add `from domain.enums import Side` to imports, then replace:

```python
# Line 131: side="BUY", → side=Side.BUY,
# Line 139: side="SELL", → side=Side.SELL,
```

Note: Lines 65/77/126/137 compare `signal_str` from DataFrame — these are borderline. Since `Side(str, Enum)`, `Side.BUY == "BUY"` is True, so comparing `signal_str == Side.BUY` works. Replace these too for consistency.

- [ ] **Step 7: Fix replay/models.py type annotations**

In `src/analytics/replay/models.py`, add `from domain.enums import Side` to imports:

```python
# Line 209: side: str → side: Side
# Line 253: side: str → side: Side
# Line 282: self.side == "BUY" → self.side == Side.BUY  (works with Side enum)
# Line 336: DomainSide.BUY if position.side == "BUY" → Side.BUY if position.side == Side.BUY
# Line 371: side="BUY" if pos.quantity > 0 else "SELL" → side=Side.BUY if ... else Side.SELL
```

- [ ] **Step 8: Remove DomainSide alias from paper/models.py**

In `src/analytics/paper/models.py`:
```python
# Line 16: Remove "Side as DomainSide" — use Side directly (OrderSide alias already removed)
```

- [ ] **Step 9: Run tests and lint**

```bash
ruff check src/analytics/ --fix && ruff format src/analytics/
pytest tests/unit/analytics/ -x -q
```

- [ ] **Step 10: Commit**

```bash
git add src/analytics/
git commit -m "refactor(ref-2): replace string BUY/SELL with Side enum in analytics"
```

---

## Task 2: REF-3 — Replace Hardcoded "NSE" Defaults with DEFAULT_EXCHANGE

**Files:**
- Modify: `src/domain/entities/trade.py` (line 22)
- Modify: `src/domain/orders/requests.py` (lines 41, 90)
- Modify: `src/domain/ports/oms_backtest_adapter.py` (line 66)
- Modify: `src/domain/conventions.py` (line 109)
- Modify: `src/domain/portfolio/account_view.py` (lines 119, 132)
- Modify: `src/domain/value_objects/instrument_metadata.py` (line 90)
- Modify: `src/domain/instruments/display_names.py` (lines 225, 226)
- Modify: `src/domain/instruments/derivatives_math.py` (lines 203, 205, 208)
- Modify: `src/domain/extensions/facade.py` (line 146)
- Modify: `src/analytics/replay/models.py` (line 281)
- Modify: `src/analytics/backtest/fast_backtest.py` (lines 198, 225)
- Modify: `src/analytics/scanner/models.py` (line 217)
- Modify: `src/analytics/paper/models.py` (line 176)
- Modify: `src/analytics/strategy/evaluator_bridge.py` (line 29)
- Modify: `src/infrastructure/time_service.py` (line 20)
- Modify: `src/infrastructure/historical_data.py` (line 236)
- Modify: `src/infrastructure/adapters/market_data_gateway_adapter.py` (lines 80, 255, 269)
- Modify: `src/infrastructure/providers/csv/csv_data_provider.py` (line 202)
- Modify: `src/infrastructure/providers/broker/broker_data_provider.py` (lines 228, 249)
- Modify: `src/infrastructure/providers/dataframe/dataframe_data_provider.py` (line 145)
- Modify: `src/application/services/instrument_registry.py` (line 335)
- Modify: `src/application/streaming/tick_router.py` (lines 206, 244)
- Modify: `src/application/streaming/orchestrator.py` (lines 414, 415)
- Modify: `src/application/composer/factory.py` (line 58)
- Modify: `src/application/streaming/live_tick_pipeline.py` (lines 54, 63)
- Modify: `src/application/oms/extended_order_service.py` (line 100)
- Modify: `src/application/data/historical_coordinator.py` (line 35)
- Modify: `src/application/oms/live_order_authority.py` (line 130)
- Modify: `src/application/oms/position_manager.py` (line 263)
- Modify: `src/application/execution/execution_engine.py` (line 121)
- Modify: `src/application/oms/_internal/daily_pnl_tracker.py` (line 115)
- Modify: `src/config/endpoints.py` (line 171)
- Modify: `src/interface/api/routers/live/market.py` (lines 25, 54, 68, 90)
- Modify: `src/interface/api/routers/backtest.py` (line 104)
- Modify: `src/interface/api/routers/replay.py` (line 198)
- Modify: `src/interface/api/routers/orders.py` (line 169)
- Modify: `src/interface/api/routers/live/extended.py` (line 263)
- Modify: `src/interface/api/ws/feed_wiring.py` (lines 15, 63)
- Modify: `src/interface/api/schemas/_market.py` (line 37)
- Modify: `src/interface/ui/services/broker_service.py` (line 472)
- Modify: `src/interface/ui/services/cli_broker_facade.py` (line 123)
- Modify: `src/datalake/core/symbols.py` (line 94)
- Modify: `src/datalake/gateway.py` (line 128)
- Modify: `src/tradex/session.py` (line 381)

**Interfaces:**
- Consumes: `domain.constants.DEFAULT_EXCHANGE` (already defined)
- Produces: No string "NSE" defaults in function signatures

- [ ] **Step 1: Fix domain layer (highest priority)**

Add `from domain.constants import DEFAULT_EXCHANGE` to each file, then replace `exchange: str = "NSE"` → `exchange: str = DEFAULT_EXCHANGE` in:

- `src/domain/entities/trade.py:22`
- `src/domain/orders/requests.py:41,90`
- `src/domain/ports/oms_backtest_adapter.py:66`
- `src/domain/conventions.py:109`
- `src/domain/portfolio/account_view.py:119,132`
- `src/domain/value_objects/instrument_metadata.py:90`
- `src/domain/instruments/display_names.py:225,226`
- `src/domain/instruments/derivatives_math.py:203,205,208`
- `src/domain/extensions/facade.py:146`

- [ ] **Step 2: Fix analytics layer**

Add `from domain.constants import DEFAULT_EXCHANGE` to each file, then replace `"NSE"` defaults:

- `src/analytics/replay/models.py:281`
- `src/analytics/backtest/fast_backtest.py:198,225`
- `src/analytics/scanner/models.py:217`
- `src/analytics/paper/models.py:176`
- `src/analytics/strategy/evaluator_bridge.py:29`

- [ ] **Step 3: Fix infrastructure layer**

Add `from domain.constants import DEFAULT_EXCHANGE` to each file, then replace:

- `src/infrastructure/time_service.py:20`
- `src/infrastructure/historical_data.py:236`
- `src/infrastructure/adapters/market_data_gateway_adapter.py:80,255,269`
- `src/infrastructure/providers/csv/csv_data_provider.py:202`
- `src/infrastructure/providers/broker/broker_data_provider.py:228,249`
- `src/infrastructure/providers/dataframe/dataframe_data_provider.py:145`

- [ ] **Step 4: Fix application layer**

Add `from domain.constants import DEFAULT_EXCHANGE` to each file, then replace:

- `src/application/services/instrument_registry.py:335`
- `src/application/streaming/tick_router.py:206,244`
- `src/application/streaming/orchestrator.py:414,415`
- `src/application/composer/factory.py:58`
- `src/application/streaming/live_tick_pipeline.py:54,63`
- `src/application/oms/extended_order_service.py:100`
- `src/application/data/historical_coordinator.py:35`
- `src/application/oms/live_order_authority.py:130`
- `src/application/oms/position_manager.py:263`
- `src/application/execution/execution_engine.py:121`
- `src/application/oms/_internal/daily_pnl_tracker.py:115`

- [ ] **Step 5: Fix interface/config/datalake layers**

Add `from domain.constants import DEFAULT_EXCHANGE` to each file, then replace:

- `src/config/endpoints.py:171`
- `src/interface/api/routers/live/market.py:25,54,68,90`
- `src/interface/api/routers/backtest.py:104`
- `src/interface/api/routers/replay.py:198`
- `src/interface/api/routers/orders.py:169`
- `src/interface/api/routers/live/extended.py:263`
- `src/interface/api/ws/feed_wiring.py:15,63`
- `src/interface/api/schemas/_market.py:37`
- `src/interface/ui/services/broker_service.py:472`
- `src/interface/ui/services/cli_broker_facade.py:123`
- `src/datalake/core/symbols.py:94`
- `src/datalake/gateway.py:128`
- `src/tradex/session.py:381`

- [ ] **Step 6: Run tests and lint**

```bash
ruff check src/ --fix && ruff format src/
pytest tests/unit/ -x -q --timeout=60
```

- [ ] **Step 7: Commit**

```bash
git add src/
git commit -m "refactor(ref-3): replace hardcoded NSE string defaults with DEFAULT_EXCHANGE constant"
```

---

## Task 3: REF-9 — Migrate Facade Imports to Canonical Paths (Batch 1: Domain + Application)

**Files:** ~40 files across domain/ and application/

**Interfaces:**
- Consumes: `domain.enums`, `domain.entities`, `domain.market_enums`, `domain.capabilities`, `domain.orders.requests`, `domain.reconciliation`, `domain.entities.order_lifecycle`, `domain.entities.position`
- Produces: All files use canonical submodule imports

- [ ] **Step 1: Fix domain-internal facade imports (21 files using `from domain.types import`)**

For each file, replace `from domain.types import X` with the canonical `from domain.<owner> import X`:

| File | Replace with |
|------|-------------|
| `domain/execution_contracts.py:17` | `from domain.enums import Side` |
| `domain/status_mapper.py:13` | `from domain.enums import OrderStatus` |
| `domain/models/dtos.py:34` | `from domain.market_enums import ExchangeSegment` |
| `domain/market/segment_mapper.py:7` | `from domain.market_enums import ExchangeSegment` |
| `domain/entities/order.py:19-25` | `from domain.enums import OrderStatus, OrderType, ProductType, Side, Validity` |
| `domain/entities/trade.py:11` | `from domain.enums import ProductType, Side` |
| `domain/exchange_segments.py:25` | `from domain.market_enums import ExchangeSegment` |
| `domain/orders/requests.py:18-23` | `from domain.enums import OrderType, ProductType, Side, Validity` |
| `brokers/providers/dhan/segments.py:28` | `from domain.market_enums import ExchangeSegment` |
| `brokers/common/order_wire.py:9` | `from domain.market_enums import ExchangeSegment` |
| `brokers/providers/paper/segment_mapper.py:15` | `from domain.market_enums import ExchangeSegment` |
| `infrastructure/persistence/sqlite_order_store.py:30` | `from domain.enums import OrderStatus, OrderType, ProductType, Side` |
| `infrastructure/persistence/sqlite_execution_ledger.py:20` | `from domain.enums import Side` |
| `application/composer/execution.py:16` | `from domain.enums import OrderStatus` |
| `application/oms/order_manager.py:55` | `from domain.entities.order_lifecycle import ORDER_STATUS_TRANSITIONS` + `from domain.enums import OrderStatus, OrderType, ProductType, Side` |
| `application/oms/position_manager.py:21` | `from domain.entities.position import POSITION_STATE_TRANSITIONS, PositionState` |
| `application/oms/order_validator.py:18` | `from domain.enums import OrderStatus` |
| `application/oms/_internal/order_lifecycle.py:17` | `from domain.enums import OrderStatus` |
| `application/oms/_internal/order_state_validator.py:28` | `from domain.entities.order_lifecycle import ORDER_STATUS_TRANSITIONS` + `from domain.enums import OrderStatus` |
| `application/oms/_internal/order_position_updater.py:24` | `from domain.enums import OrderStatus` |
| `application/oms/_internal/order_audit_logger.py:26` | `from domain.enums import OrderStatus` |

- [ ] **Step 2: Fix application layer `from domain import` facade imports**

For each file, replace `from domain import X` with the canonical submodule import. Key files:

- `application/services/reconciliation_service.py:20` — `from domain.entities import Order, Position` + `from domain.enums import OrderStatus`
- `application/services/instrument_registry.py:33` — `from domain.entities import OptionChain`
- `application/trading/execution_planner.py:15` — `from domain.enums import OrderType, ProductType`
- `application/trading/trading_orchestrator.py:45` — `from domain.enums import OrderType, ProductType`
- `application/portfolio/context.py:21` — `from domain.entities import Balance, Position, Trade`
- `application/portfolio/portfolio_service.py:20` — `from domain.entities import Position, Trade`
- `application/portfolio/__init__.py:22` — `from domain.entities import Balance`
- `application/execution/simulated_fill.py:12` — split into entities + enums
- `application/execution/oms_backtest_adapter.py:18` — `from domain.enums import OrderType, ProductType, Side`
- `application/execution/fill_source.py:19` — `from domain.entities import Order`
- `application/execution/gateway_submit.py:10` — `from domain.entities import Order` + `from domain.enums import OrderStatus`
- `application/oms/_internal/risk_manager.py:88` — `from domain.entities import Order`
- `application/oms/order_command_mapper.py:13` — `from domain.enums import OrderType, ProductType, Side`
- `application/oms/_internal/margin_checker.py:27` — `from domain.entities import Order`

- [ ] **Step 3: Run tests**

```bash
ruff check src/domain/ src/application/ --fix && ruff format src/domain/ src/application/
pytest tests/unit/domain/ tests/unit/application/ tests/architecture/ -x -q
```

- [ ] **Step 4: Commit**

```bash
git add src/domain/ src/application/
git commit -m "refactor(ref-9): migrate domain+application facade imports to canonical submodule paths"
```

---

## Task 4: REF-9 — Migrate Facade Imports to Canonical Paths (Batch 2: Brokers + Infrastructure + Interface)

**Files:** ~65 files across brokers/, infrastructure/, interface/, datalake/

**Interfaces:**
- Consumes: Same canonical submodules as Task 3
- Produces: All broker/infra/interface files use canonical imports

- [ ] **Step 1: Fix broker layer facade imports**

Key files (85 total `from domain import` in brokers/):

- `brokers/providers/upstox/broker.py:79` — `from domain.capabilities import Capability, ConnectionStatus`
- `brokers/providers/upstox/adapters/upstox_orders.py:14-24` — split into 3 imports (entities, enums, market_enums)
- `brokers/providers/upstox/adapters/tick_translator.py:15` — `from domain.entities import Quote`
- `brokers/providers/upstox/orders/cover_order_adapter.py:15` — `from domain.entities import Order`
- `brokers/providers/upstox/orders/gtt_adapter.py:12-16` — `from domain.entities import ConditionalAlert, ConditionalAlertRequest, Order`
- `brokers/providers/upstox/orders/order_query_adapter.py:8` — `from domain.entities import Order, Trade`
- `brokers/providers/upstox/orders/alert_adapter.py:6` — `from domain.entities import ConditionalAlert, ConditionalAlertRequest`
- `brokers/providers/upstox/adapters/upstox_streaming.py:16` — `from domain.entities import MarketDepth, Quote`
- `brokers/providers/upstox/streaming_service.py:16` — `from domain.entities import MarketDepth, Quote`
- `brokers/providers/upstox/orders/slice_adapter.py:19` — `from domain.entities import Order` + `from domain.orders.requests import SliceOrderRequest`
- `brokers/providers/upstox/adapters/stream_manager.py:16` — `from domain.entities import Quote`
- `brokers/providers/upstox/mappers/derivatives_mapper.py:15-25` — split into 3 imports
- `brokers/common/api/__init__.py:18-25` — `from domain.entities import FundLimits, Holding, MarketDepth, OptionContract, Position, Quote`
- `brokers/providers/upstox/instruments/segment_mapper.py:12` — `from domain.market_enums import ExchangeSegment`
- `brokers/providers/upstox/mappers/_base.py:12-20` — split into 2 imports
- `brokers/providers/upstox/mappers/equity_mapper.py:12-19` — split into 2 imports
- `brokers/providers/upstox/orders/order_command_adapter.py:19-25` — remove `Side as OrderSide` alias, use `Side` directly
- `brokers/providers/upstox/wire.py:24-36` — split into 2 imports
- `brokers/providers/upstox/mappers/options_mapper.py:12` — `from domain.entities import OptionContract`
- `brokers/common/acl.py:12` — `from domain.enums import OrderStatus`
- `brokers/common/recon_local.py:8` — split into 2 imports
- `brokers/providers/upstox/market_data_service.py:22-27` — `from domain.entities import ...`
- `brokers/providers/dhan/websocket/publish.py:14` — `from domain.entities import DepthLevel, MarketDepth, Quote`
- `brokers/common/contracts/broker_contract.py:20-26` — split into 2 imports
- `brokers/providers/dhan/data/subscription_engine.py:16` — `from domain.entities import Quote`
- `brokers/providers/upstox/extensions/depth.py:13` — `from domain.entities import MarketDepth`
- `brokers/providers/dhan/websocket/polling_feed.py:18` — `from domain.entities import Quote`
- `brokers/common/contracts/market_coverage_contract.py:21` — `from domain.entities import Quote`
- `brokers/providers/dhan/data/depth_feed_base/__init__.py:37` — `from domain.entities import DepthLevel, MarketDepth`
- `brokers/providers/dhan/websocket/order_stream.py:22-30` — split into 2 imports
- `brokers/providers/dhan/order_capabilities.py:11` — `from domain.entities import OrderResponse`
- `brokers/providers/dhan/extensions/depth20.py:13` — `from domain.entities import MarketDepth`
- `brokers/providers/upstox/market_intelligence/snapshot.py:15` — `from domain.entities import MarketIntelligenceSnapshot`
- `brokers/providers/dhan/data/market_data.py:11` — `from domain.entities import DepthLevel, MarketDepth, Quote`
- `brokers/providers/dhan/status_mapper.py:9` — `from domain.enums import OrderStatus`
- `brokers/providers/dhan/data/depth_parser.py:20` — `from domain.entities import DepthLevel, MarketDepth`
- `brokers/providers/dhan/streaming/connection.py:37` — `from domain.entities import MarketDepth`
- `brokers/providers/dhan/extensions/depth200.py:11` — `from domain.entities import MarketDepth`
- `brokers/providers/dhan/domain.py:14` — `from domain.entities import Holding, Order, Position, Trade`
- `brokers/providers/dhan/__init__.py:47` — split into entities + reconciliation
- `brokers/providers/dhan/data/depth_20.py:17` — `from domain.entities import MarketDepth`
- `brokers/providers/dhan/data/depth_200.py:36` — `from domain.entities import MarketDepth`
- `brokers/providers/upstox/status_mapper.py:9` — `from domain.enums import OrderStatus`
- `brokers/providers/dhan/wire.py:25` — `from domain.entities import Balance, MarketDepth, OrderResponse, Quote`
- `brokers/providers/upstox/websocket/market_data_v3.py:34` — `from domain.entities import Quote`
- `brokers/providers/upstox/capabilities/orders.py:8` — `from domain.entities import OrderResponse` + `from domain.orders.requests import OrderRequest`
- `brokers/providers/dhan/execution/super_orders.py:18` — `from domain.entities import OrderResponse`
- `brokers/providers/dhan/portfolio/portfolio.py:13` — split into 2 imports
- `brokers/providers/dhan/execution/forever_orders.py:18` — `from domain.entities import OrderResponse`
- `brokers/providers/dhan/execution/orders.py:27-35` — split into 2 imports, remove `Side as OrderSide`
- `brokers/providers/dhan/execution/order_validator.py:15` — `from domain.enums import OrderType, ProductType`
- `brokers/providers/dhan/portfolio/reconciliation.py:16` — `from domain.reconciliation import DriftItem, ReconciliationReport`
- `brokers/providers/paper/paper_market_data.py:8` — `from domain.entities import DepthLevel, MarketDepth, Quote`
- `brokers/providers/paper/paper_gateway.py:12-24` — split into 2 imports
- `brokers/providers/paper/paper_orders.py:9-18` — split into 2 imports
- `brokers/providers/paper/sim_config.py:8` — `from domain.enums import Side`
- `brokers/providers/dhan/execution/order_placement.py:24-32` — split into 2 imports, remove `Side as OrderSide`
- `brokers/providers/dhan/execution/order_cancellation.py:16` — split into 2 imports
- `brokers/providers/paper/paper_portfolio.py:7` — `from domain.entities import Balance, Holding, Position`
- `brokers/providers/upstox/reconciliation/service.py:18` — `from domain.reconciliation import DriftItem, ReconciliationReport`
- `interface/ui/commands/market_handlers.py:15` — `from domain.entities import DepthLevel, MarketDepth`

Also remove `Side as OrderSide` aliases from:
- `brokers/providers/dhan/execution/orders.py:35`
- `brokers/providers/dhan/execution/order_placement.py:32`
- `brokers/providers/upstox/orders/order_command_adapter.py:25`

- [ ] **Step 2: Fix infrastructure + interface + datalake layer**

- `infrastructure/persistence/sqlite_order_store.py:30` — `from domain.enums import OrderStatus, OrderType, ProductType, Side`
- `infrastructure/persistence/sqlite_execution_ledger.py:20` — `from domain.enums import Side`
- `interface/api/routers/_trades.py:10` — `from domain.enums import OrderStatus`
- `interface/ui/services/renderers.py:11` — `from domain.entities import DepthLevel, MarketDepth, Position`
- `interface/ui/services/broker_service.py:20` — `from domain.entities import Order` + `from domain.enums import Side`
- `interface/api/routers/orders.py:12` — `from domain.enums import OrderStatus, OrderType, ProductType, Side`
- `datalake/gateway.py:31` — `from domain.entities import MarketDepth, Quote`

- [ ] **Step 3: Run tests**

```bash
ruff check src/ --fix && ruff format src/
pytest tests/unit/ tests/architecture/ -x -q --timeout=60
```

- [ ] **Step 4: Commit**

```bash
git add src/
git commit -m "refactor(ref-9): migrate broker/infra/interface facade imports to canonical submodule paths"
```

---

## Task 5: REF-5 — Consolidate Simulation Models (Phase 1: Config + Trade + Position)

**Files:**
- Modify: `src/analytics/simulation/models.py` (expand from 12 lines)
- Modify: `src/analytics/paper/models.py` (thin adapter)
- Modify: `src/analytics/replay/models.py` (thin adapter)
- Modify: `src/analytics/shared/trade_types.py` (delete or absorb)

**Interfaces:**
- Consumes: `domain.enums.Side`, `domain.enums.PositionSide`, `domain.trading_costs`
- Produces: `analytics.simulation.models.SimConfig`, `SimTrade`, `SimPosition`, `SimSession`

- [ ] **Step 1: Create shared Config in simulation/models.py**

Define a base `SimConfig` dataclass with common fields (initial_capital, slippage_pct, commission_model, fill_model, warmup_bars). `PaperConfig` and `ReplayConfig` inherit from it adding mode-specific fields.

- [ ] **Step 2: Unify SimTrade**

Create `analytics/simulation/trade.py` with a unified `SimTrade` dataclass using `Side` enum (not str). Both `PaperTrade` and `SimulatedTrade` become aliases or thin subclasses.

- [ ] **Step 3: Unify SimPosition**

Create `analytics/simulation/position.py` with a unified `SimPosition` using `PositionSide` enum (not str). Both `PaperPosition` and `SimulatedPosition` become aliases.

- [ ] **Step 4: Make paper/replay models thin adapters**

`PaperConfig = SimConfig` (or subclass with extra fields). Same for `ReplayConfig`.

- [ ] **Step 5: Run tests**

```bash
pytest tests/unit/analytics/ -x -q
```

- [ ] **Step 6: Commit**

```bash
git add src/analytics/
git commit -m "refactor(ref-5): consolidate paper/replay simulation models (phase 1)"
```

---

## Task 6: REF-11 — Replace High-Impact dict[str, Any] with Typed Models

**Files:**
- Modify: `src/application/oms/extended_order_service.py` (9 occurrences)
- Modify: `src/domain/entities/options.py` (greeks field)
- Modify: `src/analytics/walk_forward/engine.py` (5 occurrences)
- Modify: `src/analytics/replay/state_assertor.py` (5 occurrences)
- Modify: `src/analytics/replay/models.py` (4 internal occurrences)
- Modify: `src/domain/analytics/statistics.py` (2 occurrences)
- Modify: `src/analytics/core/models.py` (3 internal occurrences)
- Modify: `src/analytics/strategy/models.py` (2 occurrences)
- Modify: `src/analytics/backtest/models.py` (1 occurrence)

**Interfaces:**
- Consumes: Existing dataclass/Pydantic patterns in codebase
- Produces: Typed dataclasses replacing `dict[str, Any]`

- [ ] **Step 1: Create typed models for analytics**

Create typed dataclasses for the highest-impact replacements:
- `ExtendedOrderPayload` for `application/oms/extended_order_service.py`
- `Greeks` for `domain/entities/options.py`
- `WindowResult` for `analytics/walk_forward/engine.py`
- `StateDiff` for `analytics/replay/state_assertor.py`
- `ReplayMetadata` for `analytics/replay/models.py`

- [ ] **Step 2: Replace dict[str, Any] with typed models**

Replace each `dict[str, Any]` field with its typed equivalent.

- [ ] **Step 3: Run tests**

```bash
pytest tests/unit/domain/ tests/unit/analytics/ tests/unit/application/ -x -q
```

- [ ] **Step 4: Commit**

```bash
git add src/
git commit -m "refactor(ref-11): replace high-impact dict[str, Any] with typed models"
```

---

## Task 7: REF-14 + REF-15 — Guardrails and mypy Strict Expansion

**Files:**
- Modify: `mypy-strict-allowlist.txt` (expand)
- Modify: `.pre-commit-config.yaml` (add CI hook if missing)
- Modify: `pyproject.toml` (ruff rules if needed)

**Interfaces:**
- Consumes: All prior tasks (clean code to add to strict allowlist)
- Produces: Expanded mypy strict coverage, CI duplication detection

- [ ] **Step 1: Expand mypy strict allowlist**

Add these modules (verified clean of dict[str, Any]):
- `domain/parsing.py`
- `domain/risk/notional.py`
- `domain/options/chain_normalizer.py`
- `domain/instruments/_derivatives.py`
- `domain/instruments/_specialized.py`
- `domain/primitives/value_objects.py`
- `domain/executions/result.py`
- `analytics/simulation/trade_mapping.py`
- `analytics/simulation/signal_processor.py`
- `analytics/simulation/fill_recorder.py`
- `analytics/simulation/position_closer.py`

- [ ] **Step 2: Run mypy strict on new modules**

```bash
mypy --strict src/domain/parsing.py src/domain/risk/notional.py ...
```

- [ ] **Step 3: Add CI duplication detection**

Add a simple AST-based check script that detects >80% similarity between analytics sub-packages >100 lines.

- [ ] **Step 4: Commit**

```bash
git add mypy-strict-allowlist.txt scripts/ .pre-commit-config.yaml
git commit -m "refactor(ref-14/ref-15): expand mypy strict coverage + add duplication detection"
```

---

## Dependency Graph

```
Task 1 (REF-2: Side enum) ─────────────┐
Task 2 (REF-3: DEFAULT_EXCHANGE) ──────┤
                                        ├── Task 4 (REF-9 batch 2)
Task 3 (REF-9 batch 1) ───────────────┤
                                        ├── Task 5 (REF-5: models)
                                        │
Task 6 (REF-11: typed models) ────────┤
                                        │
Task 7 (REF-14/15: guardrails) ───────┘
```

Tasks 1-4 are independent and can be parallelized. Task 5 depends on Task 1 (Side enum). Task 7 depends on Tasks 1-6 (needs clean code for strict allowlist).
