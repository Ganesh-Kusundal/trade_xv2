# ADR-003: Multi-Broker Abstraction & Common Gateway Architecture Audit

**System**: TradeXV2  
**Audit Date**: 2026-06-25  
**Auditor**: MiMo Code Agent  
**Scope**: Broker abstraction honesty, auto-mode routing, historical federation, WebSocket stability, composer coupling, quota governance, extensibility

---

## EXECUTIVE SUMMARY

This system exhibits **two parallel gateway abstractions** — the legacy `MarketDataGateway` ABC and the newer `CommonBrokerGateway` Protocol — that serve different orchestration layers. The newer Protocol-based design (`broker_port.py`) is architecturally sound and honest about commonality vs specialization. The legacy `MarketDataGateway` + `IntelligentGateway` layer is a flat routing facade that conflates broker selection with broker abstraction. The critical gap is that **these two layers are not cleanly separated** — the legacy `IntelligentGateway` still exists and is used by older code paths, while the new `BrokerRouter`/`Composer` stack is the intended future. This creates a split-brain architecture risk.

---

## CAPABILITY MATRIX

| Feature | Common? | Dhan | Upstox | Access Pattern | Notes |
|---------|---------|------|--------|----------------|-------|
| Place order | ✅ | ✅ | ✅ | CommonBrokerGateway.place_order | Normalized |
| Cancel order | ✅ | ✅ | ✅ | CommonBrokerGateway.cancel_order | Normalized |
| Modify order | ✅ | ✅ | ✅ | CommonBrokerGateway.modify_order | Raises Unsupported if no support |
| Positions | ✅ | ✅ | ✅ | CommonBrokerGateway.get_positions | Normalized |
| Margins/Funds | ✅ | ✅ | ✅ | CommonBrokerGateway.get_margins | Normalized |
| Order book | ✅ | ✅ | ✅ | CommonBrokerGateway.get_orders | Normalized |
| Trade book | ✅ | ✅ | ✅ | CommonBrokerGateway.get_trades | Normalized |
| Quote snapshot | ✅ | ✅ | ✅ | CommonBrokerGateway.get_quote_snapshot | Normalized |
| Depth snapshot | ✅ | ✅ | ✅ | CommonBrokerGateway.get_depth_snapshot | Level varies |
| Historical bars | ✅ | ✅ | ✅ | CommonBrokerGateway.get_historical_bars | Single-broker slice |
| Market stream | ✅ | ✅ | ✅ | CommonBrokerGateway.open_market_stream | Lifecycle by StreamOrchestrator |
| Order stream | ✅ | ✅ | ✅ | CommonBrokerGateway.open_order_stream | Lifecycle by StreamOrchestrator |
| Health check | ✅ | ✅ | ✅ | CommonBrokerGateway.health | |
| Depth 20 WS | ❌ | ✅ | ❌ | DeepDepthProvider extension | Dhan-only |
| Depth 200 WS | ❌ | ✅ | ❌ | DeepDepthProvider extension | Dhan-only |
| Super orders | ❌ | ✅ | ❌ | SuperOrderProvider extension | Dhan-only |
| Forever/GTT orders | ❌ | ✅ | ✅ | GttOrderProvider extension | Both via extension |
| News feed | ❌ | ❌ | ✅ | NewsProvider extension | Upstox-only |
| Fundamentals | ❌ | ❌ | ✅ | FundamentalsProvider extension | Upstox-only |
| Market intelligence | ❌ | ❌ | ✅ | MarketIntelligencePort extension | Upstox-only |
| Native slice orders | ❌ | ✅ | ❌ | SliceOrderCommand extension | Dhan-only |
| Cover orders | ❌ | ✅ | ❌ | CoverOrderProvider extension | Dhan-only |
| Conditional alerts | ❌ | ✅ | ❌ | ConditionalAlertProvider extension | Dhan-only |
| Portfolio stream | ❌ | ❌ | ✅ | BrokerCapabilities.supports_portfolio_stream | Upstox-only |
| Expired options history | ❌ | ✅ | ❌ | BrokerCapabilities.supports_expired_options_history | Dhan-only |

**Rate Limits:**

| Endpoint Class | Dhan RPS | Upstox RPS | Dhan Cooldown | Upstox Cooldown |
|---------------|----------|------------|---------------|-----------------|
| orders | 25.0 | 10.0 | 130s | 60s |
| quotes | 6.0 | 1.0 | 130s | 60s |
| historical | 6.0 | 5.0 | 130s | 60s |
| option_chain | 3.0 | 5.0 | 130s | 60s |

**Historical Window Constraints (1m timeframe):**

| Broker | Max Lookback Days | Max Chunk Days | Expired Instruments |
|--------|-------------------|----------------|---------------------|
| Dhan | 3650 | 90 | Yes |
| Upstox | 30 | 30 | No |

---

## FINDINGS

---

### FINDING 1

---
🔴 [CRITICAL] DUAL GATEWAY ABSTRACTION CREATES SPLIT-BRAIN ARCHITECTURE
Location: `brokers/common/gateway.py` (MarketDataGateway) vs `brokers/common/broker_port.py` (CommonBrokerGateway)
Concern Type: Common Interface Pollution
Diagnosis: Two incompatible gateway protocols coexist — the legacy `MarketDataGateway` ABC (synchronous, flat, broker-adapters implement it directly) and the newer `CommonBrokerGateway` Protocol (async, quota-gated, designed for the Composer/Router stack). The broker adapters (`DhanGateway`, `UpstoxBrokerGateway`) implement `MarketDataGateway` but NOT `CommonBrokerGateway`. The `CommonBrokerGateway` Protocol has methods like `place_order(request, quota=QuotaToken)` that take `QuotaToken` and return `OrderResponse` — but the concrete gateways don't have these signatures.
Operational Consequence: The new Composer/Router/QuotaScheduler stack (`ExecutionComposer`, `MarketDataComposer`) calls `CommonBrokerGateway` methods that don't exist on the concrete gateways. This means the "v2" architecture is either not yet wired to real broker adapters, or there is an adapter layer between them that is not visible in the codebase.
Prescription: Either (a) make concrete gateways implement `CommonBrokerGateway` by adding the `list_capabilities()`, `get_historical_bars()`, `open_market_stream()` methods with `QuotaToken` parameters, or (b) create an adapter layer that wraps the legacy `MarketDataGateway` into a `CommonBrokerGateway`-compliant object. Remove or deprecate the legacy `MarketDataGateway` ABC once the new Protocol is the primary interface.
---

### FINDING 2

---
🔴 [CRITICAL] INTELLIGENTGATEWAY IS A FLAT ROUTING FACADE DISGUISED AS A COMMON GATEWAY
Location: `brokers/common/intelligent_gateway.py`
Concern Type: Auto Mode Risk | Common Interface Pollution
Diagnosis: `IntelligentGateway` hardcodes routing decisions (LTP → Upstox, History → Dhan, Depth → Dhan) with try/except fallback chains. It has no concept of `OperationKind`, `SourceSelectionPolicy`, or `QuotaToken`. It is a God Object that combines broker selection, caching, health-based failover, and degraded-mode serving — all in one 605-line class. Its `_route()` method uses `getattr(self, f"_{primary}")` string-based dispatch, which is fragile and untestable. The new `BrokerRouter` + `SourceSelectionPolicy` architecture is the correct replacement, but `IntelligentGateway` is still present and likely still in use by older code paths.
Operational Consequence: Two routing systems can conflict. The `IntelligentGateway` routes to Upstox for LTP regardless of health state unless `BrokerHealthMonitor` is injected. The `BrokerRouter` uses policy-driven selection. If both are active, different code paths get different routing decisions.
Prescription: Deprecate `IntelligentGateway` entirely. Ensure all code paths go through `BrokerRouter` + `SourceSelectionPolicy`. The `IntelligentGateway` can be retained as a thin backward-compatibility wrapper that delegates to `BrokerRouter` during migration, but it must not contain its own routing logic.
---

### FINDING 3

---
🟠 [HIGH] COMMONBROKERGATEWAY PROTOCOL METHODS NOT IMPLEMENTED BY CONCRETE GATEWAYS
Location: `brokers/dhan/gateway.py`, `brokers/upstox/gateway.py`
Concern Type: Common Interface Pollution
Diagnosis: The `CommonBrokerGateway` Protocol defines `list_capabilities()`, `supports()`, `get_historical_bars(request, quota=...)`, `open_market_stream(plan)`, `open_order_stream(plan)`, `health()`. The concrete gateways implement `capabilities()` (returning the old `BrokerCapabilities`), `history()`, `stream()` — but NOT the Protocol methods. The `BrokerRegistry.register()` calls `gateway.list_capabilities()` which would fail on the concrete gateways.
Operational Consequence: The `BrokerRegistry`, `BrokerRouter`, `HistoricalDataCoordinator`, and `StreamOrchestrator` components cannot operate against the real broker adapters without an adapter layer.
Prescription: Create adapter classes (`DhanBrokerPortAdapter`, `UpstoxBrokerPortAdapter`) that wrap the concrete gateways and implement the `CommonBrokerGateway` Protocol. Register these adapters, not the raw gateways, into the `BrokerRegistry`.
---

### FINDING 4

---
🟠 [HIGH] TWO SEPARATE BROKER CAPABILITIES DATA CLASSES
Location: `brokers/common/capabilities.py:BrokerCapabilities` vs `brokers/common/gateway.py:BrokerCapabilities`
Concern Type: Normalization Leak
Diagnosis: Two distinct `BrokerCapabilities` dataclasses exist. The one in `capabilities.py` is the authoritative version (240+ fields with `supports_*` flags, `RateLimitProfile`, `HistoricalWindowConstraint`, `StreamLimitProfile`). The one in `gateway.py` is a simpler 20-field version used by the legacy `MarketDataGateway.capabilities()`. The concrete gateways return the legacy version.
Operational Consequence: Capability information is fragmented. The new `BrokerRegistry` uses the rich `capabilities.py` version; the legacy `IntelligentGateway` and `MarketDataGateway` use the sparse version. Any capability query through the old path misses critical information like `rate_limit_profiles`, `historical_windows`, `stream_limits`, `latency_class`, `reliability_class`.
Prescription: Delete the legacy `BrokerCapabilities` in `gateway.py`. Have the concrete gateways return the authoritative `BrokerCapabilities` from `capabilities.py`. This is a breaking change to `MarketDataGateway.capabilities()` return type but necessary for correctness.
---

### FINDING 5

---
🟠 [HIGH] BROKER EXTENSION INTERFACES NOT WIRED TO BROKER REGISTRY FOR DISCOVERY
Location: `brokers/common/extensions/__init__.py`, `brokers/common/registry.py`
Concern Type: Extensibility Problem
Diagnosis: `ExtensionRegistry` and `ExtensionBundle` exist and have a clean `require(broker_id, ExtensionType)` API. `BrokerRegistry` has `get_extensions()`. However, the `register()` method on `BrokerRegistry` takes an optional `ExtensionBundle` but the concrete gateways don't provide bundles. The `DhanGateway.extended` property returns a `DhanExtendedCapabilities` object but this is not registered in the `ExtensionRegistry`. Upstox has `UpstoxExtendedCapabilities` similarly unregistered.
Operational Consequence: Application code cannot use `extensions.require("dhan", SuperOrderProvider)` because no bundle is registered. The extension system exists but is not connected to real broker registrations.
Prescription: At bootstrap, register `ExtensionBundle`s for each broker containing the typed extension implementations. For Dhan: `SuperOrderProvider`, `GttOrderProvider`, `ConditionalAlertProvider`, `SliceOrderCommand`, `CoverOrderProvider`. For Upstox: `NewsProvider`, `FundamentalsProvider`, `MarketIntelligencePort`.
---

### FINDING 6

---
🟠 [HIGH] STREAMORCHESTRATOR CALLS Gateway.open_market_stream() BUT CONCRETE GATEWAYS IMPLEMENT stream()
Location: `brokers/common/stream_orchestrator.py:397`, `brokers/dhan/gateway.py:449`
Concern Type: WebSocket Stability Gap
Diagnosis: `StreamOrchestrator._open_session()` calls `gw.open_market_stream(plan)` where `plan` is a `BrokerStreamPlan`. The concrete gateways implement `stream(symbol, exchange, mode, on_tick)` — a completely different signature. The `open_market_stream(plan) -> BrokerStreamHandle` method is defined in the `CommonBrokerGateway` Protocol but not implemented by the concrete gateways.
Operational Consequence: The `StreamOrchestrator` cannot open WebSocket sessions through the real broker adapters without an adapter layer. The new stream orchestration architecture is disconnected from the real WebSocket implementations.
Prescription: Create adapter implementations that translate `open_market_stream(plan)` into the broker-specific `stream()` calls, returning a `BrokerStreamHandle` that wraps the real WebSocket connection.
---

### FINDING 7

---
🟠 [HIGH] HISTORICAL DATA FEDERATION ARCHITECTURALLY COMPLETE BUT NOT WIRED
Location: `brokers/common/historical_coordinator.py`
Concern Type: Historical Data Federation
Diagnosis: The `HistoricalDataCoordinator` is well-designed: it partitions ranges by broker capability (`_partition_ranges`), chunks by `max_chunk_days`, validates overlaps with configurable tolerance, records provenance, detects gaps, and supports degraded-mode fallback. However, it calls `gw.get_historical_bars(request, quota=quota)` — a method that doesn't exist on the concrete gateways (they have `history()`). The coordinator cannot actually fetch data.
Operational Consequence: Multi-broker historical federation cannot execute against real brokers. The 689-line coordinator is dead code from the perspective of real broker adapters.
Prescription: Wire the coordinator through an adapter that implements `CommonBrokerGateway.get_historical_bars()`. The adapter should translate `HistoricalBarRequest` into the broker's `history()` call, converting between the Protocol's normalized `HistoricalBar` and the concrete gateway's `pd.DataFrame`.
---

### FINDING 8

---
🟠 [HIGH] QUOTA SCHEDULER GATEWAY METHODS REQUIRE QUOTA TOKEN BUT CONCRETE GATEWAYS DON'T ACCEPT THEM
Location: `brokers/common/quota_scheduler.py`, `brokers/dhan/gateway.py:80`
Concern Type: Quota Governance Gap
Diagnosis: The `QuotaScheduler` produces `QuotaToken` objects. The `CommonBrokerGateway` Protocol requires `quota: QuotaToken` on every mutating and quota-consuming call. The concrete gateways (`DhanGateway.place_order()`, `UpstoxBrokerGateway.place_order()`) don't accept `QuotaToken` parameters. The quota system exists but cannot be enforced at the gateway level.
Operational Consequence: Quota enforcement is advisory only. A caller can bypass the `QuotaScheduler` entirely and call gateway methods directly without acquiring a token. Historical backfill could exhaust all quota while orders are in flight.
Prescription: Either (a) add `quota: QuotaToken` to concrete gateway methods and validate at the gateway entry point, or (b) have the adapter layer validate tokens before delegating to the concrete gateway.
---

### FINDING 9

---
🟡 [MEDIUM] BROKERROUTER IS WELL-DESIGNED BUT NOT TESTED AGAINST REAL BROKERS
Location: `brokers/common/router.py`
Concern Type: Auto Mode Risk
Diagnosis: `BrokerRouter` implements capability-based filtering, health-based filtering, quota-aware scoring, latency-aware scoring, and parallel source selection. The `SourceSelectionPolicy` dataclass is clean and injectable. However, there are no integration tests that wire the router to real broker health snapshots and verify end-to-end routing decisions.
Operational Consequence: Routing correctness is only validated in unit tests with mocked registries. A misconfigured policy or an unexpected health state could route execution to the wrong broker.
Prescription: Add integration tests that: (a) register both brokers with real capabilities, (b) set health states, (c) verify routing decisions match policy expectations, (d) verify quota-aware scoring selects the broker with more headroom.
---

### FINDING 10

---
🟡 [MEDIUM] STREAM FAILOVER DOES NOT MODEL SOURCE SWITCHING SAFETY
Location: `brokers/common/stream_orchestrator.py:542-600`
Concern Type: WebSocket Stability Gap
Diagnosis: The reconnect loop reconnects to the same broker (`session.broker_id`). There is no logic to switch to a different broker on sustained staleness. The `SubscriptionRequest.allow_failover` flag exists but the reconnect loop doesn't use it to try a fallback broker. The `_select_broker` method only runs at initial subscription time.
Operational Consequence: If the primary broker's WebSocket becomes permanently unhealthy (not just disconnected), the session will keep retrying the same broker with exponential backoff until it gives up. No failover to the other broker occurs.
Prescription: When a session exceeds `max_reconnect_attempts` on the same broker, and `allow_failover=True`, the orchestrator should attempt to open a new session on a fallback broker, migrate subscriptions, and deliver a handoff event to consumers.
---

### FINDING 11

---
🟡 [MEDIUM] COMPOSER LAYER DEPENDS ON BROKER INFRASTRUCTURE TYPES
Location: `application/composer/execution.py:14`, `application/composer/market_data.py:13`
Concern Type: Composer Coupling
Diagnosis: The composers import from `brokers.common.broker_port`, `brokers.common.models`, `brokers.common.registry`, `brokers.common.router`, `brokers.common.historical_coordinator`, `brokers.common.stream_orchestrator`. The application layer depends directly on infrastructure types. This violates the Dependency Rule (domain ← application ← infrastructure). The composers should depend on domain ports, not infrastructure implementations.
Operational Consequence: The application layer cannot be tested independently of the broker infrastructure. Mocking requires constructing infrastructure types.
Prescription: Define domain-level ports for the operations the composers perform (e.g., `HistoricalDataPort`, `StreamPort`, `OrderExecutionPort`) and have the infrastructure types implement those ports. The composers should depend on domain ports.
---

### FINDING 12

---
🟡 [MEDIUM] BROKER HEALTH MONITOR TRACKS ONLY CONSECUTIVE FAILURES, NOT LATENCY OR ERROR RATE
Location: `brokers/common/resilience/broker_health_monitor.py`
Concern Type: WebSocket Stability Gap
Diagnosis: `BrokerHealthMonitor` has a simple threshold model: 5 consecutive failures → unhealthy, 1 success → healthy. It doesn't track latency, error rate, or time-since-last-success. The `BrokerHealthSnapshot` in `models.py` has `error_rate` and `latency_p50_ms` fields, but the monitor doesn't populate them.
Operational Consequence: A broker that responds slowly (high latency) but never throws exceptions is considered healthy. A broker with 40% error rate but 60% success rate stays healthy because consecutive failures never reach 5.
Prescription: Extend the monitor to track a sliding window of outcomes (success/failure/latency) and compute error_rate and latency_p50. The `BrokerHealthSnapshot` fields exist but are unused.
---

### FINDING 13

---
🟢 [LOW] FACTORY FUNCTION `BrokerProviderFactory` RETURNS `MarketDataGateway` NOT `CommonBrokerGateway`
Location: `brokers/common/factory.py`
Concern Type: Extensibility Problem
Diagnosis: The `BrokerProviderFactory` abstract factory returns `MarketDataGateway` (the legacy ABC). The `create_composers()` factory in `application/composer/factory.py` expects `CommonBrokerGateway`. These two factory systems are disconnected.
Operational Consequence: Adding a new broker requires implementing `MarketDataGateway` for the old path AND `CommonBrokerGateway` for the new path — double the work.
Prescription: Update `BrokerProviderFactory.create()` to return `CommonBrokerGateway`. Have the concrete factories produce adapter-wrapped gateways.
---

## COMMON GATEWAY VERDICT

### What belongs in the true common interface (`CommonBrokerGateway` Protocol)

The Protocol in `broker_port.py` is **architecturally correct**. It exposes only operations that are universally meaningful across brokers:

- `place_order`, `cancel_order`, `modify_order` (normalized)
- `get_positions`, `get_margins`, `get_orders`, `get_trades` (normalized)
- `get_quote_snapshot`, `get_depth_snapshot` (normalized)
- `get_historical_bars` (single-broker slice; federation handled by coordinator)
- `open_market_stream`, `open_order_stream` (lifecycle owned by StreamOrchestrator)
- `health`, `close`
- `list_capabilities`, `supports`

**Verdict**: This is an honest interface. It does not force broker-specific features into the common contract.

### What must move to broker-specific extension interfaces

Already correctly identified in `brokers/common/extensions/`:
- `SuperOrderProvider`, `GttOrderProvider`, `ConditionalAlertProvider`, `CoverOrderProvider` (Dhan)
- `NewsProvider`, `FundamentalsProvider`, `MarketIntelligencePort` (Upstox)
- `DeepDepthProvider` (Dhan — depth-20/200 WS)
- `SliceOrderCommand` (Dhan)
- `NativeSliceOrder` (Dhan)

**Verdict**: The extension model is sound. The gap is that extensions are not wired to the registry at bootstrap.

### What should be handled by the broker router / policy engine

Already correctly identified:
- `SourceSelectionPolicy` with per-operation-class routing
- `BrokerRouter` with capability/health/quota-aware selection
- `ExecutionPolicy.execution_account` decouples market-data routing from execution account

**Verdict**: The policy engine is well-designed. The gap is that the concrete gateways don't implement the Protocol that the router expects.

---

## AUTO MODE DESIGN

### Separate policies for each operation class

The `SourceSelectionPolicy` already defines:
- `historical: RoutingPolicy` — parallel federation mode
- `live_market_data: RoutingPolicy` — priority list with fallback
- `execution: RoutingPolicy` — fixed to execution account
- `enrichment: RoutingPolicy` — capability match (Upstox-only for news)
- `instrument_metadata: RoutingPolicy` — priority list

**Verdict**: This is the correct design. Execution is explicitly fixed to one broker. Historical uses parallel sources. Live data falls back.

### Execution identity vs market-data identity

The `RoutingPolicy.execution_account` field correctly decouples these:
- Market data can come from Upstox (faster batch operations)
- Orders always go to the user's chosen execution broker (Dhan by default)
- The router logs which broker was selected and why

**Verdict**: This is architecturally correct and safe.

### Observability

Every routing decision is logged as a structured `routing.decision` event with `trace_id`, `primary_broker`, `fallback_brokers`, `parallel_brokers`, `reason_codes`, `rejected`, `policy_version`, `decided_at`.

**Verdict**: Full audit trail exists.

---

## HISTORICAL DATA FEDERATION DESIGN

### What exists

- `HistoricalDataCoordinator` (689 lines) — full federation logic
- `ProvenanceLedger` — complete audit trail
- Range partitioning by broker capability (`_partition_ranges`)
- Chunk splitting by `max_chunk_days`
- Concurrent fetch with semaphore-bounded parallelism
- OHLCV conflict detection with configurable tolerance (10 bps default)
- Merge strategies: `prefer_primary`, `prefer_newest_provenance`, `fail_on_conflict`
- Gap detection and degraded-mode fallback
- Source provenance preserved per bar via `HistoricalBar.provenance`

### What's missing

- Wiring to concrete gateways (adapter layer needed)
- Timezone normalization (bars from different brokers may have different timezone conventions)
- Corporate action adjustment normalization
- Volume semantics normalization (Dhan vs Upstox may count differently)
- Open interest field normalization

**Verdict**: Architecturally complete but not connected to real adapters. Bar normalization beyond OHLCV values needs attention.

---

## STREAM ORCHESTRATION DESIGN

### What exists

- `StreamOrchestrator` (698 lines) — centralized lifecycle management
- `StreamSession` with orthogonal health dimensions: `TransportState`, `SubscriptionState`, `FreshnessState`
- Reconnect with exponential backoff (1s base, 60s max)
- Heartbeat monitoring (5s interval)
- Staleness detection (configurable `freshness_sla_s`)
- Consumer fan-out with `asyncio.wait_for(timeout=1.0)` for slow consumer protection
- Session reuse for same broker + stream kind
- State transition logging with structured events

### What's missing

- Cross-broker failover (reconnect only retries same broker)
- Duplicate tick suppression after reconnect
- Subscription state recovery after reconnect (re-subscribe on reconnect)

**Verdict**: Solid foundation. Cross-broker failover is the critical gap.

---

## TARGET REPOSITORY STRUCTURE

```
brokers/
  common/
    broker_port.py              # CommonBrokerGateway Protocol (KEEP AS-IS)
    capabilities.py             # Authoritative BrokerCapabilities (KEEP AS-IS)
    models.py                   # OperationKind, RouteDecision, etc. (KEEP AS-IS)
    errors.py                   # Error hierarchy (KEEP AS-IS)
    registry.py                 # BrokerRegistry (KEEP AS-IS)
    router.py                   # BrokerRouter (KEEP AS-IS)
    policy.py                   # SourceSelectionPolicy (KEEP AS-IS)
    quota_scheduler.py          # QuotaScheduler (KEEP AS-IS)
    historical_coordinator.py   # HistoricalDataCoordinator (KEEP AS-IS)
    stream_orchestrator.py      # StreamOrchestrator (KEEP AS-IS)
    provenance.py               # ProvenanceLedger (KEEP AS-IS)
    extensions/                 # Extension interfaces (KEEP AS-IS)
    adapters/
      dhan_port_adapter.py      # NEW: wraps DhanGateway → CommonBrokerGateway
      upstox_port_adapter.py    # NEW: wraps UpstoxBrokerGateway → CommonBrokerGateway
  dhan/
    gateway.py                  # Existing (deprecate legacy ABC methods)
    broker.py                   # Keep
    connection/                 # Keep
    extended/                   # Keep
  upstox/
    gateway.py                  # Existing (deprecate legacy ABC methods)
    broker.py                   # Keep
    adapters/                   # Keep
    extended/                   # Keep
  legacy/
    gateway.py                  # MOVE MarketDataGateway here (deprecated)
    intelligent_gateway.py      # MOVE IntelligentGateway here (deprecated)
```

---

## REFACTORING ROADMAP

### Phase 1: Wire the new Protocol to real adapters (SAFE)

1. Create `DhanBrokerPortAdapter` that wraps `DhanGateway` and implements `CommonBrokerGateway`
2. Create `UpstoxBrokerPortAdapter` that wraps `UpstoxBrokerGateway` and implements `CommonBrokerGateway`
3. Register adapters in `BrokerRegistry` at bootstrap
4. Verify `BrokerRouter` makes correct routing decisions against real capabilities

### Phase 2: Wire historical federation (SAFE)

5. Implement `get_historical_bars()` in adapters, translating `HistoricalBarRequest` → `gateway.history()`
6. Wire `HistoricalDataCoordinator` through `MarketDataComposer`
7. Integration test: fetch 60-day 1m data → verify Upstox gets recent 30d, Dhan gets prior 30d
8. Verify provenance ledger records correct chunk assignments

### Phase 3: Wire stream orchestration (MEDIUM RISK)

9. Implement `open_market_stream()` in adapters, returning `BrokerStreamHandle` wrapping real WS
10. Wire `StreamOrchestrator` through `MarketDataComposer`
11. Integration test: subscribe to NIFTY LTP → verify health transitions, reconnect behavior
12. Add cross-broker failover when primary broker exceeds max reconnect attempts

### Phase 4: Wire quota enforcement (MEDIUM RISK)

13. Add `quota: QuotaToken` validation to adapter entry points
14. Verify `ExecutionComposer` quota acquisition → gateway call → release flow
15. Integration test: exhaust historical quota → verify execution quota still available

### Phase 5: Wire extensions (SAFE)

16. At bootstrap, register `ExtensionBundle`s for each broker
17. Verify `extensions.require("dhan", SuperOrderProvider)` returns correct implementation
18. Verify `extensions.require("upstox", NewsProvider)` returns correct implementation

### Phase 6: Deprecate legacy layer (BREAKING)

19. Mark `MarketDataGateway` ABC as deprecated
20. Mark `IntelligentGateway` as deprecated
21. Migrate all remaining callers to use `Composer`/`Router` stack
22. Remove legacy layer once all callers are migrated

---

## SEVERITY SUMMARY

| Severity | Count | Key Issues |
|----------|-------|------------|
| 🔴 Critical | 3 | Dual gateway abstraction, IntelligentGateway routing, Protocol not implemented |
| 🟠 High | 5 | Two capabilities classes, extensions not wired, stream adapter gap, quota not enforced, historical not wired |
| 🟡 Medium | 4 | Router not integration-tested, no cross-broker failover, composer depends on infra types, health monitor too simple |
| 🟢 Low | 1 | Factory returns wrong type |

---

## NON-NEGOTIABLE RULES — VERIFICATION

| Rule | Status |
|------|--------|
| Common interface models TRUE commonality | ✅ `CommonBrokerGateway` is honest |
| Broker-specific power not lost | ⚠️ Extension model exists but not wired |
| Auto mode is a policy engine | ✅ `SourceSelectionPolicy` + `BrokerRouter` |
| Historical merge without normalization is data corruption | ⚠️ OHLCV normalization exists; timezone/corporate-action normalization missing |
| WS not healthy because TCP is open | ✅ `StreamSession` models transport + subscription + freshness separately |
| Execution identity ≠ market-data identity | ✅ `execution_account` field on policy |
| Adding third broker doesn't touch core common gateway | ⚠️ Needs adapter registration only — but adapter code must be written |
