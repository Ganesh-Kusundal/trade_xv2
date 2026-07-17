# Architectural Audit — Trade_XV2 (Shotgun Surgery & Coupling)

> Deep audit regenerated 2026-07-17 against commit `6d4615b6` (graphify-first, evidence-verified).
> Supersedes the prior shallow WebSocket-centric version of this file.
> Scope: `src/` (1,165 Python files, ~158.6k LOC). Method: graphify orientation → grep/read line
> verification → parallel evidence gathering across patterns A–H. Every finding below has a
> verified `file:line`. Prior partial fixes (segments.py, ws.py, DEFAULT_EXCHANGE, Extension ABC,
> upstox/bundles) are accounted for as "partially landed" where relevant.

---

## Phase 1 — Codebase Mapping

### 1.1 Top-level packages and responsibilities

| Package | Files | Stated responsibility | As-built reality |
|---|---:|---|---|
| `src/domain/` | 231 | Typed entities, ports (Protocols), events, constants. No inbound imports. | **Clean inward** (verified: no imports of application/infra/runtime/brokers/interface). But holds *two* parallel canonical stores (`constants/market.py` vs `constants/exchanges.py` vs `market/hours.py`) and dead code (`RiskGate`). |
| `src/application/` | 105 | Use-cases: oms, execution, trading, portfolio, composer, streaming, scheduling. | Static-clean of infra/runtime imports (import-linter green). Contains god-objects (`oms/context.py` 665, `trading_orchestrator.py` 610, `composer/factory.py` 527) and cross-module private mutation. |
| `src/infrastructure/` | 119 | Cross-cutting adapters: resilience, persistence, event_bus, mappers, connection, observability. | Duplicates domain mappers (`mappers/order_mapper.py`), reaches into broker privates (`connection/authenticated_readiness.py`), lazy-imports runtime. |
| `src/runtime/` | 28 | Composition root — ONLY layer touching concrete brokers/plugins. | Verified **0** string-broker branching inside `runtime/`. Broker builders isolated (sanctioned import-linter ignores). |
| `src/brokers/` | 323 | Dhan / Upstox / Paper adapters + `brokers/services` SDK + `brokers/common` + `brokers/cli`. | Largest package. Parallel Dhan/Upstox trees with no shared base; heaviest duplication surface (orders, price, reconnect, timestamps, circuit breakers). |
| `src/datalake/` | 58 | Ingestion/quality/storage/analytics over DuckDB. | Raw `pd.DataFrame` read path (known gap). Re-implements symbol normalization, market-hours, IST, expected-candles formulas. |
| `src/analytics/` | 122 | Indicators, scanners, backtest, replay, paper, pipeline. | Mirrors `replay/` vs `paper/` structure (models/signal_processor/position_closer). Lazy-imports infrastructure (analytics→infra boundary leak). |
| `src/interface/` | 152 | FastAPI / Textual / Click / MCP presentation over the SDK. | Highest reach-through density: CLI/API probe `gw._broker`/`gw._conn` privates; 15 broker-id branches in one file; string branching hotspot. |
| `src/plugins/` | 5 | Exchange calendar/adapter plugins (NSE). | Duplicates `normalize_symbol` and IST/timezone locally. |
| `src/config/` | 14 | `endpoints.py` + Pydantic app config. | Canonical for URLs, but duplicated by `infrastructure/config/settings.py`. |
| `src/tradex/` | 8 | Public SDK package + CLI + session wiring. | Acts as a *second* composition root; mutates broker/session privates; string branching in `session_mode.py`. |

### 1.2 Dependency direction (verified)

Import-linter contract lives in `pyproject.toml:317–514` (16 contracts) and is enforced by
`tests/architecture/test_module_boundaries_and_decomposition.py:84` (`lint-imports`).
**Verified now: 16 kept, 0 broken.** Static layering is clean.

However, the linter permits sanctioned exceptions and cannot see dynamic/lazy imports. The
architecture.md contract is stricter than what the linter enforces. Delta (debt not caught):

- `infrastructure/broker_infrastructure.py:8` → `runtime.*` (sanctioned re-export)
- `infrastructure/gateway/factory.py:121–125` → lazy `runtime.broker_builders` (sanctioned)
- `infrastructure/io/async_compat.py:61,87`, `observability/http_server.py:364` → lazy `runtime.event_loop`
- `analytics/replay/orchestrator.py:133,215` → lazy `infrastructure.event_log` / `event_bus` (**not sanctioned**)
- `interface/ui/services/broker_ops.py:7–16`, `broker_service.py:401`, `cli_broker_facade.py:140`,
  `commands/certify.py:9` → `brokers.services` / `brokers.platform_ops` (architecture.md §3 rule 5 warns against interface→brokers)
- `tradex/cli.py:22–23` → concrete `brokers.cli` (tradex→brokers)

### 1.3 Shared vocabulary — where the canonical lives and who ignores it

| Concept | Canonical source | Duplicated / bypassed in |
|---|---|---|
| Exchange default `"NSE"` | `domain/constants/market.py:49` `DEFAULT_EXCHANGE` | ~85 files still hardcode `"NSE"` |
| Derivatives default `"NFO"` | `domain/constants/market.py:52` `DEFAULT_DERIVATIVES_EXCHANGE` | ~15 files hardcode `"NFO"` |
| Wire segment `"NSE_EQ"` | `domain/constants/exchanges.py:16` `WIRE_NSE_EQ` | ~12 files |
| NSE-eligible segment set | `domain/constants/segments.py:18` `nse_eligible_segments()` (**fix landed**) | still tuple-literal at `dhan/streaming/connection.py:417,467` |
| Timezone IST | `domain/constants/market.py:102` `IST` | ~8 files hardcode `"Asia/Kolkata"`; **`infrastructure/time_service.py` and `domain/ports/time_service_impls.py` duplicate the exchange→TZ map** |
| Market hours 09:15/15:30 | `domain/market/hours.py:18–19` **and** `domain/constants/market.py:57–66` (two parallel canonicals) | ~12 files |
| Order side | `domain/enums.py:14–15` `Side` | ~25 files use `"BUY"`/`"SELL"` strings |
| Product type | `domain/enums.py:60` `ProductType` | ~20 files use `"INTRADAY"`/`"MIS"` strings |
| Order status | `domain/enums.py:25` `OrderStatus` + `domain/status_mapper.py` | ~8 files use `"OPEN"`/`"PENDING"` strings |
| Field mapping (wire→domain) | `domain/field_mapping.py:12` `DefaultFieldMapping` | **near-verbatim copy** `infrastructure/mappers/order_mapper.py:34` |
| Symbol normalization | `domain/symbols.py:19` `normalize_symbol` | re-implemented `infrastructure/instruments.py:15`, `plugins/exchanges/nse/adapter.py:55`; bypassed by raw `.upper().strip()` in CLI |
| Wire price float | `domain/value_objects/price.py:65` `to_wire_float` | Dhan regular orders use `str(price)` (`order_placement.py:325`) |
| Resilience constants | `domain/constants/resilience.py`, `domain/constants/ws.py` (**fix landed**) | re-read via `os.getenv` in `market_feed.py:574,612`, `order_stream.py:219` |
| API base URLs | `config/endpoints.py:47,434` | `infrastructure/config/settings.py:27`, `infrastructure/pool/connection_pool.py:121` |

---

## Phase 2 — Shotgun Surgery Detection

Findings ordered by blast radius (highest first). Impact = HIGH on real-money order/feed/risk paths.

---

### [SMELL-1] Hardcoded `"NSE"` default exchange (Pattern A)
- **Symbol/Value:** literal `"NSE"` vs `domain/constants/market.py:49` `DEFAULT_EXCHANGE`
- **Blast Radius:** ~85 files. **Impact: HIGH**
- **Representative files (real-money):** `domain/orders/requests.py:42,91`, `domain/entities/trade.py:33`,
  `application/trading/trading_orchestrator.py:94`, `application/composer/execution.py:359`,
  `application/oms/extended_order_service.py:97`, `application/execution/execution_engine.py:112`,
  `application/streaming/tick_router.py:198,236`, `brokers/services/orders.py:82`,
  `brokers/services/market_data.py:16,35,53,75,106,122,146,180`,
  `brokers/session/broker_session.py:117,124,127,133,167,346`,
  `infrastructure/mappers/order_mapper.py:44`, `interface/ui/commands/order_placement.py:82,367`,
  `interface/api/routers/orders.py:162`, `brokers/dhan/websocket/order_stream.py:368,391`,
  `brokers/dhan/portfolio/reconciliation.py:213,246,261`, `tradex/session.py:433`.
- **Silent-failure note:** the partial `DEFAULT_EXCHANGE` migration means the *same order-ingest
  concept* now behaves inconsistently by file (see SMELL-11).

### [SMELL-2] Order side / product / status as strings instead of enums (Pattern A)
- **Symbol/Value:** `"BUY"`/`"SELL"` (`Side`), `"INTRADAY"`/`"MIS"` (`ProductType`), `"OPEN"`/`"PENDING"` (`OrderStatus`)
- **Blast Radius:** ~25 (side) + ~20 (product) + ~8 (status) files. **Impact: HIGH**
- **Side:** `domain/field_mapping.py:38`, `infrastructure/mappers/order_mapper.py:47`,
  `brokers/services/orders.py:78,93`, `brokers/dhan/wire.py:114`, `brokers/upstox/wire.py:140`,
  `brokers/paper/paper_orders.py:64`, `brokers/dhan/execution/order_placement.py:199`,
  `brokers/upstox/mappers/_base.py:65,126`, `equity_mapper.py:176`, `derivatives_mapper.py:304`.
- **Product:** `domain/orders/requests.py:48,95`, `brokers/*/wire.py`, `brokers/session/broker_session.py:311,323`,
  `brokers/dhan/execution/order_placement.py:203`, and **`interface/ui/commands/oms.py:54` defaults `"MIS"`**
  while everything else uses `"INTRADAY"`.
- **Domain-knowledge flag:** MIS≈INTRADAY on NSE, but the string divergence risks a mapping miss for
  a real order's margin product. Confirm mapping is total.

### [SMELL-3] Fragmented "place order" feature — 4 entry spines + duplicate adapter-layer risk (Pattern E)
- **Symbol/Value:** `place_order` across interface/application/brokers
- **Blast Radius:** ~17 files. **Impact: HIGH**
- **Entry spines (should be one):**
  `interface/ui/commands/order_placement.py:46` (ExecutionComposer),
  `interface/ui/services/cli_broker_facade.py:120` (ExecutionEngine→PlaceOrderUseCase),
  `interface/api/routers/orders.py:129` (tradex session), `brokers/services/orders.py:73` (BrokerSession.buy/sell, bypasses composer).
- **Spine body:** `application/composer/execution.py:77,291` → `application/oms/order_manager.py:304`
  → `application/scheduling/quota_scheduler.py:180` → `infrastructure/adapters/market_data_gateway_adapter.py:142`
  → `brokers/dhan/wire.py:110` / `brokers/upstox/wire.py:139` → adapters.
- **Duplicate risk check:** OMS validates, then Dhan `execution/order_placement.py:154–177` **and**
  Upstox `orders/order_command_adapter.py:63–67` run a *second* risk check.
  **Domain-knowledge flag:** intentional defense-in-depth vs silent divergence is unverified.

### [SMELL-4] Extended orders (super/forever/cover/OCO) — separate dict-based spine, CLI bypasses OMS (Pattern E + G)
- **Symbol/Value:** `place_super_order`/`place_cover_order`/`place_forever_order`; payload is `dict[str, Any]`, not `OrderRequest`
- **Blast Radius:** ~12–14 files. **Impact: HIGH**
- **Files:** `interface/api/routers/live/extended.py:114,350` → `application/oms/extended_order_service.py:172,289`
  → `domain/extensions/extended_order.py:55` → `brokers/dhan/extensions/common_extensions.py:160` /
  `brokers/upstox/common_extensions.py:192` → `brokers/dhan/execution/super_orders.py:40` /
  `forever_orders.py:40` / `brokers/upstox/orders/cover_order_adapter.py:23` / `gtt_adapter.py:68`.
- **Bypass (HIGH):** `interface/ui/commands/extended_orders.py:68,82,231` call the raw gateway
  (`gw._broker.gtt`, `gw._broker.cover`) directly — **skips OMS risk, idempotency, and events**.
- **`extended_order_service.py:74,106–110`** rebuilds an `Order` from the dict; on failure it falls
  back to kill-switch-only checking (a typed-model gap, Pattern G).

### [SMELL-5] Duplicated order wire↔domain mapping (Pattern B)
- **Symbol/Value:** `DefaultFieldMapping`, `from_broker_dict`, `to_order`, `order_from_response`, `_broker_order_from_response`
- **Blast Radius:** 13 files. **Impact: HIGH — DIVERGED**
- **Files:** `domain/field_mapping.py:12–69` vs near-copy `infrastructure/mappers/order_mapper.py:34–78`;
  `domain/entities/order.py:143`, `brokers/dhan/execution/orders.py:45,228`, `order_placement.py:289–369`,
  `brokers/upstox/mappers/derivatives_mapper.py:289–321`, `equity_mapper.py:166`,
  `brokers/upstox/orders/order_command_adapter.py:234`, `application/execution/gateway_submit.py:20`,
  `application/composer/execution.py:369`, `brokers/common/acl.py:15`, `brokers/common/order_wire.py:12`.
- **Divergences (verified):** exchange default differs between the two `DefaultFieldMapping` copies
  (SMELL-11); four distinct "response→Order" builders; Dhan vs Upstox timestamp parsing differs.

### [SMELL-6] Duplicated WebSocket reconnect / backoff — 3 divergent stacks (Pattern B)
- **Symbol/Value:** reconnect loop + exponential backoff (with/without jitter)
- **Blast Radius:** 9 files (+2 helpers). **Impact: HIGH — DIVERGED**
- **Stacks:** (a) Dhan `websocket/connection.py:231–374` inline loop → `brokers/common/backoff.py:10` (no jitter);
  (b) Dhan `api/reconnecting_service.py:53–184` linear-multiply (no jitter), used by `websocket/order_stream.py`;
  (c) Upstox `websocket/v3_auto_reconnect.py` → `brokers/common/transport.py:17` + `transport_policy.py:61` (±20% jitter),
  also `market_data_v3.py:206–331`, `portfolio_stream.py:84–142`.
- **Dead abstraction:** `transport_policy.for_dhan_ws()` (`:46–49`) exists but is **not wired** into the Dhan feed.
- **Risk:** reconnect timing differs per feed → parity/failover drift under real-time disconnects.

### [SMELL-7] Duplicated timestamp / timezone normalization — 4 pipelines (Pattern B)
- **Symbol/Value:** OHLCV DataFrame parsing + IST/UTC coercion
- **Blast Radius:** 7 files. **Impact: HIGH — DIVERGED (5.5h drift class)**
- **Files:** `domain/candles/_helpers.py:36–85`, `_constructors.py:24–101`, `brokers/dhan/data/historical.py:124–169`
  (UTC epoch), `brokers/upstox/adapters/historical_adapter.py:62–70,192–211` (IST), `datalake/ingestion/normalize.py:44–79`
  (naive→assume IST), `datalake/ingestion/converter.py:37–61`, `infrastructure/historical_data.py:150–160`.
- **Note:** this class already caused the documented datalake tz corruption; three independent
  "expected candles" formulas (375 vs 6.25×rate) compound it (SMELL-9).

### [SMELL-8] Hardcoded `"NFO"` derivatives default (Pattern A)
- **Symbol/Value:** `"NFO"` vs `DEFAULT_DERIVATIVES_EXCHANGE`
- **Blast Radius:** ~15 files. **Impact: HIGH (options/futures paths)**
- **Files:** `domain/universe.py:100,117`, `domain/instrument_resolver.py:50`, `domain/entities/options.py:23`,
  `domain/options/gateway_facade.py:24,34`, `brokers/session/broker_session.py:137,155`,
  `brokers/dhan/extended.py:257,262,265`, `brokers/dhan/extended_data.py:23,29,61,127,131`,
  `application/services/instrument_registry.py:150,233,274,299`, `datalake/core/symbols.py:107,135`,
  `interface/api/routers/live/derivatives.py:20,36`, `interface/ui/commands/market.py:31,138,274`.

### [SMELL-9] Market-hours & expected-candles literals scattered (Pattern A)
- **Symbol/Value:** `time(9,15)`/`time(15,30)`, `"09:15:00"`, `375`, `6.25`, `255`
- **Blast Radius:** ~12 files. **Impact: HIGH (data-quality gates)**
- **Two parallel canonicals:** `domain/market/hours.py:18–19` (time objects) and
  `domain/constants/market.py:57–66` (int hour/minute) are not wired together.
- **Duplicators:** `value_objects/instrument_metadata.py:72,73`, `datalake/quality/health_check.py:148`,
  `brokers/certification/market_hours.py:22,23`, `datalake/mcp/tools.py:178`,
  `datalake/core/nse_calendar.py:121,127`, `datalake/quality/monitor.py:88`,
  `datalake/ingestion/loader.py:302,467`, `analytics/views/quality.py:25`.
- **Domain-knowledge flag:** `analytics/intraday/afternoon_expansion.py:35–37` uses **15:15** session end
  vs canonical **15:30** — intentional strategy window or drift; confirm.

### [SMELL-10] Cross-module private-state mutation (Pattern C)
- **Symbol/Value:** assignments to another object's `._x` (and chained `._a._b =`)
- **Blast Radius:** ~14 cross-layer sites. **Impact: HIGH**
- **Highest-risk sites:**
  `tradex/session.py:321` `gw._orders._order_manager = om`;
  `domain/session.py:96` `self._universe._broker_facade = ...`;
  `application/oms/_internal/risk_manager.py:465` `self._daily_pnl_tracker._capital_provider = ...` (stale-capital risk);
  `application/composer/factory.py:273,321` `md._gap_reconcile_pending`, `target._backfill_callback`;
  `application/oms/trade_recorder.py:300` `self._fill_reducer._seen_fill_ids.add(...)` (idempotency state);
  `interface/ui/services/broker_manager.py:150–176` `svc._active_name = BrokerId.*`.
- **Risk:** OMS/backfill/capital/idempotency desync when a private field is renamed or a rebind is missed.

### [SMELL-11] Two `DefaultFieldMapping` copies that DIVERGE on exchange default (Pattern B/A — verified)
- **Symbol/Value:** `map_exchange` fallback
- **Blast Radius:** 2 files (but on every order-ingest path). **Impact: HIGH — silent**
- **Files:** `domain/field_mapping.py:35` returns `DEFAULT_EXCHANGE`; `infrastructure/mappers/order_mapper.py:44`
  returns hardcoded `"NSE"`. Bodies are otherwise identical copies. Whichever mapper an ingest path
  picks changes the resolved exchange for an order missing an explicit exchange.

### [SMELL-12] Reconciliation calls a non-existent method — silent live failure (Pattern E — verified)
- **Symbol/Value:** `TradingContext.attach_reconciliation_service`
- **Blast Radius:** ~10 files (recon feature); the bug itself is 1 call site + 1 missing def. **Impact: HIGH**
- **Verified:** `interface/ui/services/oms_bootstrap.py:190,204` call `tc.attach_reconciliation_service(...)`;
  grep of all of `src/` finds **no `def attach_reconciliation_service`** anywhere (only these calls + a docstring at `:90`).
  The call is wrapped in `try/except Exception` that only logs `broker_reconciliation_attach_failed`.
- **Consequence:** on the `oms_bootstrap` live path, broker reconciliation **silently never attaches** —
  local OMS state does not heal against broker truth. This is a real-money reconciliation gap
  (unless another path constructs `TradingContext(reconciliation_service=...)` in `__init__`; `context.py:231`
  supports the constructor arg, so live safety depends entirely on which bootstrap path runs).

### [SMELL-13] Law-of-Demeter reach-through into broker gateway internals (Pattern H)
- **Symbol/Value:** `gw._broker.*`, `gw._conn.*`, `getattr(obj, "_private")`
- **Blast Radius:** ~12 interface/infra call sites. **Impact: HIGH**
- **Files:** `interface/ui/commands/extended_orders.py:85,102,115,117,130,146,178,205,231,246,250,265`;
  `interface/ui/services/cli_broker_facade.py:44,200` (`_svc._trading_context.order_manager`);
  `interface/ui/services/oms_bootstrap.py:181–194,227,358–381`;
  `interface/ui/commands/websocket.py:40–80`; `interface/api/routers/live/webhook.py:66,73`;
  `interface/api/routers/live/extended.py:184,200,244,287,319`;
  `infrastructure/connection/authenticated_readiness.py:59–67,291–332`;
  `infrastructure/connection/bootstrap_result.py:30–48`; `domain/instruments/instrument.py:318–328`.
- **Risk:** any broker gateway refactor breaks CLI/API/auth probes opaquely.

### [SMELL-14] Broker-identity branching outside the composition root (Pattern D)
- **Symbol/Value:** `== "dhan"/"upstox"/"paper"`, `broker_id ==`, `_active_name ==`, `if bid == BrokerId.*`
- **Blast Radius:** 71 lines / 29 files (0 inside `runtime/`). **Impact: HIGH**
- **Hotspots:** `interface/ui/commands/extended_orders.py` (15 `BrokerId` gates),
  `interface/ui/services/broker_manager.py` (7, incl. `_active_name` assignments :150–176),
  `tradex/session_mode.py:27,54,56,66` (`broker_id == "paper"`),
  `infrastructure/connection/authenticated_readiness.py:249–261` (`_PROBE/_REFRESH/_SKIP` string dispatch),
  `application/execution/execution_mode_adapter.py:63` (`mode == "paper"`).
- **Invariant violated:** architecture.md §3 rule 4 ("no `_active_name` string branching elsewhere").

### [SMELL-15] Duplicated circuit-breaker / rate-limit wiring per broker (Pattern B)
- **Symbol/Value:** `_get_circuit_breaker`, `_categorize_endpoint`, CB construction
- **Blast Radius:** 7 HTTP files (+2 unrelated "loss" CBs). **Impact: HIGH — DIVERGED**
- **Files:** Dhan `api/http_client.py:236–318` vs sync/async twin `api/async_http_client.py:412–419`;
  Upstox builds CBs in **two** places with different thresholds: `auth/http.py:142–165` vs `auth/context.py:119–145`.
  Shared `infrastructure/resilience/{circuit_breaker,rate_limiter,retry_executor}.py` exist but wiring is copied.
- **Naming collision:** three unrelated "circuit breaker" concepts (HTTP infra CB, `application/oms/_internal/loss_circuit_breaker.py`, `domain/risk/policy.py DailyLossCircuitBreaker`).

### [SMELL-16] `30_000` ms / `failure_threshold=5` resilience magics (Pattern A)
- **Symbol/Value:** `30_000`, `5` vs `domain/constants/resilience.py:13,22,28`
- **Blast Radius:** 6 files. **Impact: HIGH**
- **Files:** `brokers/dhan/resilience/circuit_breaker.py:25,28`, `brokers/dhan/config/config.py:153,250`,
  `brokers/upstox/auth/http.py:136,138,155,161,163`, `brokers/upstox/auth/context.py:122`,
  `infrastructure/resilience/broker_health_monitor.py:10`.

### [SMELL-17] Duplicated price / tick / wire-float logic; Dhan bypasses canonical (Pattern B — verified)
- **Symbol/Value:** `snap_to_tick`, `to_wire_float`, paisa↔rupee
- **Blast Radius:** 9 files. **Impact: HIGH — DIVERGED**
- **Files:** `domain/value_objects/price.py:18–78` vs `domain/conventions.py:57–87` (`snap_to_tick` mirrored,
  comment admits it), vs `brokers/upstox/mappers/price_parser.py:14–33` (`to_paisa/to_rupee` re-impl).
- **Verified divergence:** Dhan regular orders send **`str(request.price)`** (`order_placement.py:325–330`)
  while Upstox and Dhan extended/margin paths send **`to_wire_float(request.price)`**. Same OMS path,
  different wire precision/format.

### [SMELL-18] Staleness `60.0`s and reconnect-attempts `50` re-read via `os.getenv` (Pattern A)
- **Symbol/Value:** `60.0`, `50` vs `domain/constants/ws.py:14,17` (fix landed but not fully adopted)
- **Blast Radius:** ~10 (staleness) + 4 (attempts) files. **Impact: HIGH**
- **Files:** `brokers/dhan/websocket/market_feed.py:574–575,612` and `order_stream.py:219` re-read env
  instead of importing the constant `connection.py` already uses.
- **Cross-broker inconsistency:** `application/streaming/reconnect_controller.py:54` caps attempts at **5**
  vs Dhan **50** — inconsistent failover semantics for the same disconnect class.

### [SMELL-19] Symbol-normalization split-brain (Pattern B/D — F8)
- **Symbol/Value:** `normalize_symbol` / `normalize_symbol_for_storage`
- **Blast Radius:** 5 parallel implementations. **Impact: MEDIUM (HIGH at OMS/registry key boundary)**
- **Files:** canonical `domain/symbols.py:19` (delegated correctly by `datalake/core/symbols.py:25`),
  but re-implemented in `infrastructure/instruments.py:15–33`, `plugins/exchanges/nse/adapter.py:55`,
  and bypassed by raw `.upper().strip()` in `interface/ui/commands/market.py:26,137,273`.
- **Risk:** `RELIANCE-EQ` stripped to `RELIANCE` in storage/instrument paths but kept as `RELIANCE-EQ`
  in CLI paths → partition-key vs trading-key mismatch.

### [SMELL-20] Kill-switch fragmented across 4 surfaces; domain `RiskGate` is dead code (Pattern E + G)
- **Symbol/Value:** kill switch; `RiskGate`
- **Blast Radius:** ~8 files. **Impact: HIGH**
- **Surfaces:** OMS `application/oms/_internal/kill_switch.py:26` + `risk_manager.py:360`; composer
  `composer/execution.py:66`; extended `extended_order_service.py:70`; broker-native
  `brokers/dhan/extended.py:121` / `brokers/upstox/kill_switch/client.py:16` (invoked from CLI
  `extended_orders.py:256`).
- **Dead abstraction:** `domain/risk/policy.py:160 RiskGate` has **zero instantiations** in `src/`
  (grep `RiskGate(` → none); production uses `application/oms/_internal/risk_manager.py`.
- **Domain-knowledge flag:** an operator toggling the OMS kill switch may not freeze the broker-native
  path (and vice-versa). Confirm these are intentionally independent.

### [SMELL-21] Parallel Dhan/Upstox class trees with no shared base (Pattern F)
- **Symbol/Value:** facade / wire / data_provider / order_adapter / instrument_adapter / reconciliation / capabilities
- **Blast Radius:** ~16–20 files for a cross-broker parity feature. **Impact: HIGH (maintenance)**
- **Pairs:** `dhan/streaming/connection.py DhanConnection` ↔ `upstox/broker.py UpstoxBroker`;
  `dhan/wire.py DhanWireAdapter` ↔ `upstox/wire.py UpstoxWireAdapter`;
  `dhan/portfolio/reconciliation.py` ↔ `upstox/reconciliation/service.py`;
  `dhan/config/capabilities.py` ↔ `upstox/capabilities/snapshot.py`. No shared `BrokerAdapter` base class —
  both duck-type independently. **Partly inherent** to broker-specific APIs; risk is silent parity drift.

### [SMELL-22] Extension `for_instrument` copy-constructor duplicated per broker (Pattern F)
- **Symbol/Value:** `for_instrument()` + `ext._symbol/_exchange = ...`
- **Blast Radius:** ~4 files per extension. **Impact: MEDIUM (base ABC now exists)**
- **Files:** `brokers/dhan/extensions/depth20.py:74–78`, `depth200.py:67–68`, `super_order.py:44–45`,
  `forever_order.py`, `brokers/upstox/extensions/depth.py:78–79`, `news.py:42–43`.
- **Note:** `domain/extensions/base.py:22 Extension` ABC and `nse_eligible_segments()` (fix landed) removed
  the `_NSE_SEGMENTS` frozenset duplication, but the instance-binding boilerplate still repeats.
- **Naming collision:** two different `UpstoxNewsExtension` classes (`extensions/news.py` vs `common_extensions.py:28`).

### [SMELL-23] Raw `pd.DataFrame` / raw dict leak vs typed domain models (Pattern G)
- **Symbol/Value:** candles, quotes, positions, extended-order payloads
- **Blast Radius:** ~8 leak points. **Impact: MEDIUM (HIGH for extended orders)**
- **Files:** wire adapters return DataFrame (`dhan/wire.py:350`, `upstox/adapters/historical_adapter.py:127`),
  converted only at `infrastructure/market_data_adapter.py:17`; `datalake/gateway.py:167,228,261` return
  raw `DataFrame`/`dict`; `application/oms/order_manager.py:409` returns list-of-dicts for reconciliation;
  extended orders carry `dict[str, Any]` end-to-end (SMELL-4).

### [SMELL-24] God-classes / god-facades (Pattern G / SRP)
- **Blast Radius:** 1 file each, but each is a shotgun-surgery magnet. **Impact: MEDIUM–HIGH**
- `application/oms/context.py` (665: OMS+recon+shutdown+equity+lifecycle+replay);
  `brokers/dhan/data/depth_feed_base.py` (708); `application/trading/trading_orchestrator.py` (610);
  `brokers/paper/paper_gateway.py` (593); `brokers/dhan/wire.py` (521: orders+history+depth+stream+portfolio);
  `application/oms/_internal/risk_manager.py` (517: risk+kill+margin+CB); `interface/ui/services/broker_service.py` (516);
  `datalake/gateway.py` (494); `brokers/upstox/broker.py` (479); `application/composer/factory.py` (527).

### [SMELL-25] Duplicated exchange-universe frozensets + endpoint URLs (Pattern A)
- **Blast Radius:** 4 (sets) + 2 (URLs) files. **Impact: MEDIUM**
- **Sets (diverge on BFO/BCD/INDEX membership):** `domain/instruments/instrument_id.py:70`,
  `interface/api/schemas/_portfolio.py:62`, `interface/ui/commands/instruments.py:44`, `instrument.py:58,85`.
- **URLs:** `config/endpoints.py:47,434` duplicated by `infrastructure/config/settings.py:27`,
  `infrastructure/pool/connection_pool.py:121`. **Domain-knowledge flag:** validation gaps if a new
  exchange is added to one list only.

---

### Phase 2 blast-radius ranking

| # | Smell | Pattern | Blast radius | Impact |
|---|---|---|---:|---|
| 1 | Hardcoded `"NSE"` default | A | ~85 | HIGH |
| 2 | Side/product/status strings vs enums | A | ~50 | HIGH |
| 3 | "place order" 4 spines + double risk | E | ~17 | HIGH |
| 8 | Hardcoded `"NFO"` default | A | ~15 | HIGH |
| 21 | Parallel Dhan/Upstox trees | F | ~16–20 | HIGH |
| 4 | Extended-order dict spine + CLI bypass | E/G | ~14 | HIGH |
| 5 | Duplicated order mapping | B | 13 | HIGH |
| 9 | Market-hours literals | A | ~12 | HIGH |
| 13 | LoD reach-through to broker internals | H | ~12 | HIGH |
| 14 | Broker-id branching outside runtime | D | 29 files/71 lines | HIGH |
| 10 | Cross-module private mutation | C | ~14 | HIGH |
| 6 | WS reconnect/backoff (3 stacks) | B | 9 | HIGH |
| 15 | CB/rate-limit wiring duplication | B | 9 | HIGH |
| 17 | Price/wire-float duplication + Dhan bypass | B | 9 | HIGH |
| 7 | Timestamp/tz pipelines | B | 7 | HIGH |
| 18 | staleness/reconnect env re-reads | A | ~14 | HIGH |
| 16 | 30_000/threshold magics | A | 6 | HIGH |
| 20 | Kill-switch 4 surfaces + dead RiskGate | E/G | ~8 | HIGH |
| 12 | Missing `attach_reconciliation_service` | E | 2 (feature ~10) | HIGH |
| 11 | Two DefaultFieldMapping copies diverge | B/A | 2 | HIGH |
| 19 | Symbol normalization split-brain | B/D | 5 | MEDIUM |
| 23 | Raw DataFrame/dict vs typed models | G | ~8 | MEDIUM |
| 25 | Exchange-set + URL duplication | A | 6 | MEDIUM |
| 22 | Extension `for_instrument` boilerplate | F | ~4/ext | MEDIUM |
| 24 | God-classes | G | 10 files | MEDIUM–HIGH |

---

## Phase 3 — Root Cause Classification

**RC1 — Missing/incomplete shared vocabulary layer.** Canonical constants and enums exist but adoption
is partial, and there are *competing* canonicals. → SMELL-1, 2, 8, 9, 16, 18, 25. Aggravator: two
market-hours canonicals (`market/hours.py` vs `constants/market.py`) and two IST exchange-TZ maps.

**RC2 — Missing single service/use-case spine (business logic in I/O & UI).** "Place order",
"extended order", "bracket/OCO", and "kill switch" each have logic in interface + application +
brokers with no single funnel. → SMELL-3, 4, 20. Aggravator: `PlaceOrderUseCase` exists but three
other spines bypass it.

**RC3 — Missing/duplicated domain model (raw dicts/DataFrames instead of typed entities).** Extended
orders carry `dict`; candles/quotes/positions leak `DataFrame`/`dict`; two `DefaultFieldMapping`
copies. → SMELL-4, 5, 11, 23.

**RC4 — Boundary/encapsulation violations (reach-through & cross-module mutation).** Import-linter is
green, but real coupling lives in `getattr(gw, "_broker")` reach-through, `x._y._z = ...` mutation,
and lazy cross-layer imports the linter can't see. → SMELL-10, 13, 14 (partly). Aggravator: broker-id
branching leaked out of the composition root into `interface/` and `tradex/`.

**RC5 — Premature/uncoordinated file splitting without a unifying interface.** Reconciliation split
into domain engine + app service + broker services + bootstrap glue produced a call to a method that
was never implemented (SMELL-12). Dhan feed split into connection/subscription/facade drives the
private-state mutation in SMELL-10. → SMELL-12, 10, 24.

**RC6 — Absent/inconsistent coding standards per author.** Same concept implemented differently:
`str(price)` vs `to_wire_float`; jitter vs no-jitter backoff; env re-read vs constant import;
`"MIS"` vs `"INTRADAY"`; two field mappings. → SMELL-5, 6, 7, 11, 15, 17, 18.

---

## Phase 4 — Refactoring Plan (dependency-ordered)

> Foundational vocabulary/typing extractions first; higher-level restructuring after. Zero-parity
> (backtest == replay == live) is the acceptance gate for anything on the order/fill path.

### REF-1 — Fix the silent reconciliation break (do first; it's a live-safety bug)
- **Root Cause:** RC5 · **Action:** Implement `TradingContext.attach_reconciliation_service(service, *, lifecycle)`
  (or repoint bootstrap to the `__init__(reconciliation_service=...)` path) and make the bootstrap
  `except` **fail loud** for real brokers instead of only logging.
- **From:** `interface/ui/services/oms_bootstrap.py:190,204` · **To:** `application/oms/context.py`
- **Touches:** `application/oms/context.py`, `interface/ui/services/oms_bootstrap.py`, `oms_setup.py:225`
- **Test:** integration test asserting a live-shaped `TradingContext` has a running reconciler after
  bootstrap (no mocks — real `TradingContext` + real Dhan/Upstox reconciliation service constructors).
- **Sequencing:** none — ship immediately.

### REF-2 — Complete the shared-vocabulary migration + collapse competing canonicals
- **Root Cause:** RC1 · **Action:** (a) Make `domain/constants/market.py` derive market-hours from
  `domain/market/hours.py` (one canonical); (b) single exchange→TZ map (delete the copy in
  `domain/ports/time_service_impls.py` **or** `infrastructure/time_service.py`); (c) sweep `"NSE"`→
  `DEFAULT_EXCHANGE`, `"NFO"`→`DEFAULT_DERIVATIVES_EXCHANGE`, `"NSE_EQ"`→`WIRE_NSE_EQ`; (d) replace
  `"BUY"/"INTRADAY"/"OPEN"` string defaults with enums.
- **From:** SMELL-1,2,8,9,16,18,25 locations · **To:** existing `domain/constants/*` + `domain/enums.py`
- **Touches:** ~120 files (mechanical). Do in slices by package (domain → brokers → application → interface → datalake).
- **Test:** extend `scripts/check_scattered_constants.py` to fail CI on new literals; type-check; side-by-side
  diff of resolved order payloads before/after on a golden fixture.
- **Sequencing:** before REF-3/REF-4 (they assume one vocabulary).

### REF-3 — Merge the two `DefaultFieldMapping` copies (kill the divergence)
- **Root Cause:** RC3/RC6 · **Action:** Delete `infrastructure/mappers/order_mapper.py`'s copy;
  re-export/import `domain/field_mapping.DefaultFieldMapping`. One `order_from_broker_dict`.
- **From:** `infrastructure/mappers/order_mapper.py:34–114` · **To:** `domain/field_mapping.py`
- **Touches:** `infrastructure/mappers/order_mapper.py` + its importers.
- **Test:** parametrized test feeding real Dhan & Upstox order dicts through the single mapper; assert
  identical `Order` for both former paths.
- **Sequencing:** after REF-2 (exchange default).

### REF-4 — One order wire-format helper on the order path (Dhan bypass fix)
- **Root Cause:** RC6 · **Action:** Route Dhan `order_placement.py` price/trigger through
  `to_wire_float` (matching Upstox); add a lint guard forbidding `str(<price>)` in `execution/`.
- **From:** `brokers/dhan/execution/order_placement.py:325–330` · **To:** `domain/value_objects/price.py`
- **Touches:** `order_placement.py` (+ guard). Consolidate `snap_to_tick`/`to_paisa`/`to_rupee` so
  `conventions.py` and `price_parser.py` delegate to `value_objects/price.py`.
- **Test:** golden wire-payload test for Dhan limit/SL orders at fractional ticks; assert canonical format.
- **Sequencing:** independent of REF-2/3.

### REF-5 — Single order use-case funnel
- **Root Cause:** RC2 · **Action:** Make `PlaceOrderUseCase` the only entry; convert
  `ExecutionComposer.place_order`, `cli_broker_facade`, API router, and `brokers/services/orders.py`
  into thin callers. Move extended orders behind the same funnel (typed request, not `dict`) so OMS
  risk/idempotency/events always run.
- **From:** SMELL-3, SMELL-4 spines · **To:** `application/execution/place_order_use_case.py` (+ a typed `ExtendedOrderRequest` in `domain/`)
- **Touches:** ~17 (standard) + ~12 (extended) files.
- **Test:** zero-parity integration — same signal produces identical fills via paper/replay/live funnel;
  assert CLI extended-order path now emits OMS events (regression for the current bypass).
- **Sequencing:** after REF-2, REF-3, REF-4. Resolve the double-risk-check question (SMELL-3) here.

### REF-6 — Reconnect/backoff + circuit-breaker consolidation
- **Root Cause:** RC6 · **Action:** One backoff (`infrastructure/resilience/backoff.py`, jittered) and
  one reconnect driver; wire Dhan feed to `transport_policy.for_dhan_ws()` (already exists, unused).
  One `_get_circuit_breaker` helper shared by Dhan sync/async + Upstox.
- **From:** SMELL-6, 15 locations · **To:** `brokers/common/transport*.py` + `infrastructure/resilience/*`
- **Touches:** 9 (reconnect) + 7 (CB) files.
- **Test:** deterministic fake-clock test asserting identical backoff schedule across Dhan feed, Dhan
  order stream, Upstox V3; reuse `test_market_feed_connection_race.py` pattern.
- **Sequencing:** independent; after REF-2 (constants).

### REF-7 — One timestamp/tz normalization pipeline
- **Root Cause:** RC6/RC3 · **Action:** All broker/datalake candle ingress funnels through
  `domain/candles/_helpers.py` parsers; delete the duplicated tz heuristics in
  `datalake/ingestion/{normalize,converter}.py` and `infrastructure/historical_data.py`.
- **From:** SMELL-7 · **To:** `domain/candles/_helpers.py`
- **Touches:** 7 files.
- **Test:** the existing tz regression suite (`test_historical.py`, `test_parsing.py`,
  `test_validation.py`) must pass; add a cross-broker fixture asserting Dhan(UTC) and Upstox(IST) bars
  land on identical IST index.
- **Sequencing:** independent; high value given prior corruption incident.

### REF-8 — Encapsulate connection/gateway internals (kill reach-through & mutation)
- **Root Cause:** RC4/RC5 · **Action:** Add public methods to gateways/connections for what
  `interface/`/`infrastructure/` currently reach for (`_broker`, `_conn`, `_token_manager`, `_active_name`,
  `_order_manager`, `_capital_provider`). Route `broker_manager` broker-switch through a `BrokerService`
  method, not `svc._active_name = ...`.
- **From:** SMELL-10, 13 · **To:** gateway/connection/service public APIs
- **Touches:** ~26 sites across `interface/`, `infrastructure/`, `application/composer`, `tradex/`.
- **Test:** an architecture test (AST) forbidding `getattr(x, "_...")` and `\._[a-z]+\._` assignment
  across package boundaries (see Phase 5 guardrails).
- **Sequencing:** after REF-5 (order funnel removes the biggest reach-through group in `extended_orders.py`).

### REF-9 — Move remaining broker-id branching into the composition root / capabilities
- **Root Cause:** RC4 · **Action:** Replace `if bid == BrokerId.DHAN` capability gates in
  `interface/` and `tradex/session_mode.py` with capability queries (`caps.supports_*`) resolved once
  at wiring; delete `_active_name` string dispatch.
- **From:** SMELL-14 (29 files) · **To:** `domain/capabilities/*` + runtime wiring
- **Touches:** 29 files (mostly `interface/ui/*`).
- **Test:** extend `tests/architecture` broker-branching guard to fail on `== "dhan"/"upstox"` and
  `_active_name ==` outside `runtime/`.
- **Sequencing:** after REF-8.

### REF-10 — Decompose the god-classes behind stable interfaces
- **Root Cause:** RC5 · **Action:** Split `application/oms/context.py`, `brokers/dhan/wire.py`,
  `brokers/upstox/broker.py`, `interface/ui/services/broker_service.py` into cohesive collaborators —
  **only after** REF-5/REF-8 stabilize their public surfaces (so the split doesn't re-create SMELL-12).
- **Touches:** 4 files → focused modules.
- **Test:** public-surface regression test per class; import-linter unchanged.
- **Sequencing:** last (depends on REF-5, REF-8).

---

## Phase 5 — Structural Recommendations

### 5.1 Target directory structure (deltas from today, one-line responsibilities)

```
src/
  domain/
    constants/            # SINGLE source: market hours DERIVED from market/hours.py; one IST map
    enums.py              # Side/ProductType/OrderStatus — the only allowed order literals
    field_mapping.py      # the ONLY wire→domain mapper (infra copy deleted → REF-3)
    value_objects/price.py# the ONLY snap_to_tick / to_wire_float (conventions & upstox delegate → REF-4)
    orders/               # OrderRequest + ExtendedOrderRequest (typed; replaces dict payloads)
    extensions/base.py    # Extension ABC (exists) + shared for_instrument binding (REF-22)
    risk/                 # DELETE dead RiskGate or make RiskManager implement it (one abstraction)
  application/
    execution/place_order_use_case.py  # SINGLE order funnel (standard + extended) → REF-5
    oms/context.py        # decomposed; owns attach_reconciliation_service() → REF-1/REF-10
  infrastructure/
    resilience/           # one backoff + one circuit-breaker helper → REF-6
    candles/              # (or domain/candles) one tz pipeline → REF-7
  brokers/
    common/transport*.py  # one reconnect driver wired to for_dhan_ws()/for_upstox_ws()
    dhan/ upstox/ paper/  # thin adapters; gateways expose PUBLIC methods (no _conn/_broker reach-through)
  runtime/                # STILL the only place broker identity is branched (capabilities elsewhere)
  interface/              # thin; calls application use-cases + capability queries only
  tradex/                 # SDK; stop mutating session/gateway privates (use public wiring API)
```

### 5.2 Boundary rules (enforceable)

1. `domain/` imports nothing inward (enforced — keep).
2. `application/` never imports `infrastructure/`/`runtime/`/`brokers/`/`interface/` — **including lazy imports**
   (close the `analytics/replay/orchestrator.py` and `application/composer` gaps).
3. `infrastructure/` imports `domain/` only; broker/runtime access via injected ports, not lazy import.
4. `interface/` and `tradex/` call `application/` use-cases + `domain/` capabilities only — **no
   `brokers.services` import, no `gw._broker`/`gw._conn` reach-through.**
5. Broker identity is branched **only** in `runtime/`. Everywhere else asks capabilities.
6. No module assigns to another module's `_private` attribute. State changes go through public methods.

### 5.3 Coding standards (each traces to a finding)

1. **Exchange/segment:** never hardcode `"NSE"/"NFO"/"NSE_EQ"`; use `DEFAULT_EXCHANGE`/`DEFAULT_DERIVATIVES_EXCHANGE`/`WIRE_NSE_EQ`. (SMELL-1,8,25)
2. **Order literals:** side/product/status are `Side`/`ProductType`/`OrderStatus` enums, never strings. (SMELL-2)
3. **Wire prices:** all order/trigger prices go through `to_wire_float`; `str(<price>)` banned in `execution/`. (SMELL-17)
4. **One mapper:** `domain.field_mapping.DefaultFieldMapping` is the only wire→domain mapper. (SMELL-5,11)
5. **Resilience:** timeouts/thresholds/backoff come from `domain/constants/resilience.py`+`ws.py`; no `os.getenv` re-reads of a defined constant, no jitter/no-jitter forks. (SMELL-6,15,16,18)
6. **Timestamps:** all candle ingress uses `domain/candles/_helpers.py`; no ad-hoc `to_datetime`/`fromisoformat` in brokers/datalake. (SMELL-7)
7. **Encapsulation:** no cross-package `getattr(x, "_...")` or `x._y._z = ...`. (SMELL-10,13)
8. **Broker selection:** capability-driven; broker-id `==` only inside `runtime/`. (SMELL-14)

### 5.4 Guardrails to prevent recurrence

- **AST architecture tests** (extend `tests/architecture/`): (a) forbid `str(...price...)` in `execution/`;
  (b) forbid cross-package `getattr(_)` / `._x._y =`; (c) forbid `== "dhan"/"upstox"` and `_active_name ==`
  outside `runtime/`; (d) forbid order-literal strings where an enum exists.
- **Extend the constants linter:** `scripts/check_scattered_constants.py` (exists) → add `"NFO"`,
  `"NSE_EQ"`, `"Asia/Kolkata"`, `time(9,15)`/`"09:15:00"`, `30_000`, `60.0`, `50`, `"BUY"/"SELL"/"INTRADAY"/"OPEN"`.
- **Import-linter:** upgrade the `analytics → infrastructure` and `interface → brokers.services` warnings to
  errors once REF-5/REF-8 land; remove the sanctioned lazy `infrastructure → runtime` ignore after DI.
- **`__all__`** in every package `__init__.py`; make the `for_instrument` binding a single base-class method.
- **ADR template** requiring "Root Cause (RC1–RC6)", "Blast Radius", and "Zero-parity impact" for any new
  order/fill/feed path; keep `graphify update .` in the pre-commit chain so the graph never goes stale.

---

## Domain-knowledge items flagged (do not guess — confirm with a domain owner)

1. **Double risk check** (OMS + Dhan/Upstox adapter, SMELL-3): intentional fail-closed defense-in-depth,
   or silent divergence? Governs REF-5.
2. **CLI bracket/OCO/basket** = multiple standard orders, **not** Dhan super-order / broker-native OCO
   (SMELL-4): is non-atomic multi-leg acceptable for real money?
3. **`"MIS"` vs `"INTRADAY"`** product strings (SMELL-2): confirm the mapping is total across brokers.
4. **`afternoon_expansion.py` 15:15 vs 15:30** session end (SMELL-9): strategy window or drift?
5. **OMS kill switch vs broker-native kill switch** (SMELL-20): intentionally independent surfaces?
6. **Exchange-set membership** (BFO/BCD/INDEX differ across 4 lists, SMELL-25): which is authoritative?
