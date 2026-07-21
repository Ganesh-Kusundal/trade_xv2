# 09 — Broker Subsystem Gap Analysis

**Status:** Code vs Broker Subsystem Constitution (2026-07-20)  
**Method:** graphify-first + targeted grep + contract/certification review  
**Authority:** User-supplied "Broker Subsystem Constitution" vs `src/brokers/` and surrounding layers  
**Related:** [07-gap-analysis.md](07-gap-analysis.md) (platform-wide), [context/architecture.md](../../context/architecture.md)

---

## Architecture-fit finding (read this first)

The Broker Subsystem Constitution assumes a **monolithic broker package**:

```text
packages/brokers/{contracts, core, session, auth, mapping, ratelimit, transport, ...}
    ↓
broker implementation (dhan / upstox / paper)
    ↓
SDK
```

This repository instead uses a **hexagonal / layered architecture** enforced by import-linter and documented in `docs/constitution/`:

| Spec assumption | Actual location | Notes |
|---|---|---|
| Canonical interfaces (`IBroker`, `I*Gateway`) | `src/domain/ports/` | `BrokerAdapter`, `DataProvider`, `ExecutionProvider` — not under `brokers/` |
| Rate limiting / retry / circuit breaker | `src/infrastructure/resilience/` | Shared across brokers; not broker-package-local |
| Quota scheduler | `src/application/scheduling/quota_scheduler.py` | Application-layer coordination |
| Auth token persistence | `src/infrastructure/auth/` + per-broker `auth/` | Split by design |
| `src/brokers/` | Plugin adapters only | Dhan / Upstox / Paper + thin `common/` toolkit |

**Implication:** Most spec *capabilities* already exist — distributed across `domain/`, `infrastructure/`, `application/`, and `brokers/common/`. Gaps should be read as **behavioral or organizational mismatches**, not as a mandate to relocate code into `brokers/` (which would violate the dependency rule in `context/architecture.md` §3 and ADR-0002).

**ADR-0012 constraint:** Operator paths use `ExecutionTargetKind.PAPER`; broker plugins supply market data only; OMS owns paper capital/orders/positions. The spec's order-execution ownership must be interpreted through that boundary — broker order gateways exist for certification and future live targets, not as the primary operator execution path today.

---

## Summary

| Severity | Count | Theme | Remediation status |
|---|---|---|---|
| P0 | 3 | Live cert stubs; error leakage; session FSM | ✅ Closed (Contexts 1–3) |
| P1 | 7 | Contract suite; lifecycle events; WS; regression | ✅ Closed (Contexts 4–8) |
| P2 | 6 | Package layout; naming; caching; scheduler | ✅ Docs/decision (Context 9) |
| P3 | 4 | Docs drift; legacy SPI; rate-limit warn-only | ✅ Closed / documented |

**Remaining operational gate:** run `broker certify` / `@pytest.mark.live_readonly` against Dhan/Upstox with real credentials during market hours.

---

## Conformance matrix (spec section → verdict)

| Spec section | Verdict | Primary as-built location |
|---|---|---|
| Vision (broker-agnostic, no SDK leak) | **Exists** | `domain/ports/broker_adapter.py`; transport error mapping on Dhan/Upstox order paths |
| Repository layout | **Different (intentional)** | Flat `src/brokers/{common,dhan,upstox,paper,...}`; layout map in §G-BS-P2-1 |
| Package dependency rules | **Different (intentional)** | Domain ← infrastructure ← application ← runtime ← brokers |
| Core interfaces (`IBroker`, `I*Gateway`) | **Exists (aliased)** | Glossary maps `I*` → `BrokerAdapter` / `DataProvider` / `ExecutionProvider` |
| Session lifecycle | **Exists** | `BrokerSessionState` FSM in `domain/ports/broker_session_state.py` |
| Authentication layer | **Exists** | `brokers/common/auth/lifecycle.py`, per-broker `auth/` |
| Rate limiting | **Exists** | `infrastructure/resilience/rate_limiter.py`, `domain/capabilities/broker_capabilities.py` |
| Scheduler | **Exists (documented)** | `QuotaScheduler` + per-broker buckets; call path in `FLOWS.md` |
| Instrument mapping | **Exists** | `domain/instruments/instrument_id.py`, `brokers/common/instruments/` |
| Capabilities | **Exists** | `domain/capabilities/broker_capabilities.py` |
| Gateway architecture | **Exists** | Unified `BrokerAdapter`; gateway methods compose concerns |
| Transport layer | **Exists** | `brokers/common/http/resilient_transport.py` + per-broker HTTP/WS |
| Extensions | **Exists** | `brokers/extensions/broker_extension.py`, per-broker `extensions/` |
| Broker events | **Exists** | `BROKER_CONNECTED`/`DISCONNECTED` + `TOKEN_REFRESHED`/`EXPIRED` published |
| Caching | **Exists (ownership documented)** | Instrument/token/idempotency in brokers; historical in datalake |
| Error model | **Exists** | `InstrumentError`, `MappingError`, `RejectedOrderError`, `CapabilityError` in `domain/errors.py` |
| Testing architecture | **Exists (marker-based)** | Unit/integration/component + markers for live/regression/certification |
| Real-market certification | **Exists (probes wired)** | `brokers/certification/live_probes.py`; live credential run still operator gate |
| Quality gates | **Mostly green** | Contract + cert framework; live broker green depends on credentials |

---

## P0 — Must fix before live broker production deployment

### G-BS-P0-1 — Live certification stubs fail by design

| | |
|---|---|
| **Constitution** | Real Market Certification — token reuse, refresh, reconnect, session recovery |
| **As-built** | `BrokerCertifier` raises `RuntimeError("… not implemented for live broker")` for `_token_refresh`, `_token_expiry`, `_reconnect`, `_disconnect`, `_session_recovery` (`src/brokers/certification/suite.py:147–176`, `:358–368`) |
| **Violation** | Quality gate "Certification completes real-market suite" cannot pass for Dhan/Upstox |
| **Fix** | Wire live probes: validate saved token reuse, forced refresh, WS disconnect/reconnect, subscription restore |
| **Acceptance** | `broker certify` passes all `CertArea` entries for live brokers without stub failures |

### G-BS-P0-2 — Raw SDK/HTTP exceptions can escape subsystem

| | |
|---|---|
| **Constitution** | "No raw SDK exceptions leave subsystem"; canonical error types only |
| **As-built** | Canonical hierarchy in `domain/errors.py`; `convert_network_errors` in `infrastructure/resilience/errors.py`. Counter-example: `brokers/providers/dhan/api/transport.py` catches generic `Exception` into `OrderResult.fail(str(exc))` rather than mapping to typed errors |
| **Violation** | Silent misclassification; upstream cannot distinguish retryable vs permanent failures |
| **Fix** | Enforce error mapping at every transport boundary (HTTP + WS); architecture ratchet on bare `except Exception` in `brokers/` |
| **Acceptance** | `tests/unit/brokers/common/test_gateway_error_surface_contracts.py` green; grep ratchet: no unmapped transport exceptions |

### G-BS-P0-3 — No unified session state machine

| | |
|---|---|
| **Constitution** | Session FSM: `Created → Initializing → Authenticating → Connected → Healthy → Degraded → Recovering → Disconnected → Shutdown` |
| **As-built (2026-07-20 remediation)** | `BrokerSessionState` FSM in `domain/ports/broker_session_state.py`; composed with `BootstrapStatus`, transport/subscription/freshness in `BrokerSessionStatus` |
| **Status** | ✅ Closed — unified session aggregate implemented |
| **Acceptance** | Session state transitions documented; diagnostics expose unified state; reconnect cert uses FSM |

---

## P1 — High priority

### G-BS-P1-1 — Named `I*` gateway interfaces absent

| | |
|---|---|
| **Constitution** | `IBroker`, `IMarketDataGateway`, `IOrderGateway`, `IHistoricalGateway`, `IPortfolioGateway`, `IAccountGateway`, `IInstrumentGateway`, … |
| **As-built** | `BrokerAdapter` (`domain/ports/broker_adapter.py:44–61`) composes `DataProvider` + `ExecutionProvider` (`domain/ports/protocols.py`). Historical/portfolio/account are methods on those ports, not separate gateway protocols |
| **Violation** | Spec naming mismatch; harder to grep spec ↔ code |
| **Fix** | Document alias table in glossary (`00b-glossary.md`); optional type aliases — **do not** relocate ports into `brokers/` |
| **Acceptance** | Glossary maps every spec interface name to domain port |

### G-BS-P1-2 — Contract suite does not cover orders + auth uniformly

| | |
|---|---|
| **Constitution** | Every broker passes identical suite: place, cancel, modify, authentication |
| **As-built** | `BrokerContractSuite` (`brokers/common/contracts/broker_contract.py`) covers market data + portfolio reads + order status normalization; **not** place/cancel/modify. Orders covered separately by `BrokerAdapterContractSuite` (`tests/unit/brokers/common/contracts/test_common_broker_gateway.py`) and `BrokerCertifier`. Upstox live contracts duplicate in `tests/integration/brokers/upstox/contract/test_broker_contract.py` without inheriting `BrokerContractSuite` |
| **Violation** | Three parallel contract surfaces; Upstox drift risk |
| **Fix** | Merge order lifecycle into shared suite or enforce single inheritance chain for all three brokers |
| **Acceptance** | dhan / upstox / paper all subclass same base classes for market + order + auth |

### G-BS-P1-3 — Broker lifecycle events defined but not published

| | |
|---|---|
| **Constitution** | `BrokerConnected`, `TokenExpired`, `TokenRefreshed`, … emitted on event bus |
| **As-built** | `EventType.BROKER_CONNECTED`, `EventType.TOKEN_EXPIRED` in `domain/events/types.py:137–140`; payloads in `domain/events/payloads.py:171–182`. No publishers found outside payload definitions |
| **Violation** | Downstream modules cannot react to broker lifecycle; observability gap |
| **Fix** | Publish from session/auth layers on connect, refresh, disconnect |
| **Acceptance** | Integration test subscribes to `BROKER_CONNECTED` on `BrokerSession.connect()` |

### G-BS-P1-4 — No shared WebSocket / streaming gateway in `brokers/common/`

| | |
|---|---|
| **Constitution** | REST Gateway + WebSocket Gateway + Streaming Engine as shared abstractions |
| **As-built** | Shared: `DepthStreamHandle` (`brokers/common/streaming.py`), `StreamHealth` models (`domain/stream_health.py`), reconnect policy (`brokers/common/transport_policy.py`). Implementations per-broker: `brokers/providers/dhan/streaming/`, `brokers/providers/upstox/adapters/streaming_gateway.py` |
| **Violation** | Duplicated reconnect/subscribe logic; harder to certify streaming uniformly |
| **Fix** | Extract minimal shared streaming port (connect, subscribe, publish-to-bus) without forcing identical wire protocols |
| **Acceptance** | New broker plugin implements one streaming adapter interface |

### G-BS-P1-5 — Error taxonomy incomplete vs spec

| | |
|---|---|
| **Constitution** | `InstrumentError`, `MappingError`, `RejectedOrder`, `CapabilityError`, … |
| **As-built (2026-07-20 remediation)** | `InstrumentError`, `InstrumentNotFoundError`, `MappingError`, `RejectedOrderError`, `CapabilityError` in `domain/errors.py`; `CapabilityMismatchError` / `CapabilityNotSupported` consolidated as aliases of `CapabilityError` |
| **Status** | ✅ Closed — domain hierarchy complete; broker-layer aliases retained for backward compat |
| **Acceptance** | Error mapping table in `docs/architecture/ERROR_TAXONOMY.md` aligned with domain types |

### G-BS-P1-6 — Historical certification does not verify gap-free data

| | |
|---|---|
| **Constitution** | "Historical data requests … produce correctly ordered, gap-free data" |
| **As-built** | `BrokerCertifier._hist` checks bar count > 0 only (`suite.py:254–265`). Gap detection exists in unit tests (`tests/unit/brokers/common/test_historical_coordinator.py`) but not in cert suite |
| **Violation** | Silent data quality failures in production analytics |
| **Fix** | Add cert check: monotonic timestamps, expected bar count vs window, gap report |
| **Acceptance** | Cert fails on injected gap fixture |

### G-BS-P1-7 — No repo-wide regression-test permanence policy

| | |
|---|---|
| **Constitution** | "Every broker bug becomes permanent regression test. Never removed." |
| **As-built** | Dhan-only enforced manifest: `tests/integration/brokers/dhan/regression/manifest.py` + `test_coverage_manifest.py`. Behavioral naming enforced by `tests/architecture/test_test_suite_uses_behavioral_names.py`. No global broker bug → test rule in `context/code-standards.md` |
| **Violation** | Upstox/paper bugs may not gain permanent guards |
| **Fix** | Extend manifest pattern to all live brokers or document broker-agnostic regression policy |
| **Acceptance** | CI gate fails when P0 capability lacks registered regression case per broker |

---

## P2 — Medium priority

### G-BS-P2-1 — Repository layout differs from spec tree

| | |
|---|---|
| **Constitution** | `packages/brokers/{core,contracts,session,auth,mapping,market,orders,portfolio,websocket,transport,ratelimit,retry,scheduler,diagnostics,events,extensions,testing,common,dhan,upstox,paper,replay}` |
| **As-built** | `src/brokers/{common,session,runtime,services,certification,diagnostics,exceptions,extensions,cli,dhan,upstox,paper}` — no top-level `contracts/`, `auth/`, `mapping/`, `ratelimit/`, `transport/`, `events/`, `testing/` |
| **Violation** | Spec navigability; onboarding friction |
| **Fix** | **Docs-only mapping table** (below); physical moves deferred — would fight layer boundaries |
| **Acceptance** | This document's layout map is authoritative for "where to find X" |

#### Layout map (spec → as-built)

| Spec path | As-built equivalent |
|---|---|
| `contracts/` | `domain/ports/` + `brokers/common/contracts/` (pytest suites, not Protocols) |
| `core/` | `brokers/runtime/` + `brokers/services/` |
| `session/` | `brokers/session/` |
| `auth/` | `brokers/common/auth/` + `brokers/{dhan,upstox}/auth/` + `infrastructure/auth/` |
| `mapping/` | `brokers/common/instruments/` + per-broker resolvers |
| `market/` | Methods on `DataProvider` + `brokers/services/market_data.py` |
| `orders/` | Methods on `ExecutionProvider` + `brokers/services/orders.py` + per-broker `execution/` |
| `portfolio/` | `DataProvider` portfolio methods + `brokers/services/portfolio.py` |
| `websocket/` | Per-broker `streaming/` / `websocket/` + `brokers/common/streaming.py` |
| `transport/` | `brokers/common/http/`, `brokers/common/transport.py`, `infrastructure/resilience/` |
| `ratelimit/` | `infrastructure/resilience/rate_limiter.py` |
| `retry/` | `infrastructure/resilience/retry_executor.py` |
| `scheduler/` | `application/scheduling/quota_scheduler.py` |
| `diagnostics/` | `brokers/diagnostics/` |
| `events/` | `domain/events/` + `infrastructure/event_bus/` |
| `extensions/` | `brokers/extensions/` + per-broker `extensions/` |
| `testing/` | `tests/unit/brokers/`, `tests/integration/brokers/`, `brokers/common/contracts/` |
| `replay/` | `analytics/replay/` (not under `brokers/`) |

### G-BS-P2-2 — Package dependency rules differ

| | |
|---|---|
| **Constitution** | `contracts → core → session → auth → mapping → ratelimit → transport → broker impl → SDK` |
| **As-built** | `domain` (ports) ← `infrastructure` (resilience) ← `application` (scheduling) ← `runtime` (composition) ← `brokers/*` (plugins). Brokers import domain + infrastructure; domain never imports brokers |
| **Violation** | Spec dependency arrow reversed vs clean architecture |
| **Fix** | Treat spec dependency section as **logical layering within broker plugin**, not repo-wide import graph |
| **Acceptance** | ADR or this doc supersedes spec dependency rule for this repo |

### G-BS-P2-3 — Scheduler shape differs (no transport-level priority queue in brokers)

| | |
|---|---|
| **Constitution** | All API calls: Scheduler → Priority Queue → Rate Limiter → Retry → Transport |
| **As-built** | Per-broker HTTP clients acquire tokens directly (`brokers/providers/dhan/api/http_client.py`, `brokers/providers/upstox/auth/http.py`) via `MultiBucketRateLimiter`. Global `QuotaScheduler` in application layer uses priority classes with max-wait deadlines, not a heap queue (`application/scheduling/quota_scheduler.py:192–199`) |
| **Violation** | Spec diagram oversimplifies; two scheduling layers may double-throttle or bypass each other |
| **Fix** | Document call path per operation class; ensure single choke point per endpoint |
| **Acceptance** | Architecture diagram in `docs/architecture/FLOWS.md` updated |

### G-BS-P2-4 — Caching incomplete vs spec

| | |
|---|---|
| **Constitution** | Broker owns instrument, historical, quote, metadata, capability, token, mapping caches |
| **As-built** | Instrument file cache (`domain/ports/data_catalog.py`), resolver in-memory maps, token stores (per-broker), idempotency (`brokers/common/idempotency.py`). **Missing:** shared quote cache, shared historical cache in `brokers/` |
| **Violation** | Duplicate historical fetches; no unified cache invalidation policy |
| **Fix** | Delegate to datalake/views for historical; document quote cache ownership (instrument refresh vs global) |
| **Acceptance** | Cache policy section in broker diagnostics |

### G-BS-P2-5 — Capabilities naming differs from spec

| | |
|---|---|
| **Constitution** | `SupportsOptions`, `SupportsBracketOrders`, `SupportsGTT`, … |
| **As-built** | `BrokerCapabilities` frozen dataclass: `supports_option_chain`, `supports_super_order`, etc. (`domain/capabilities/broker_capabilities.py`) |
| **Violation** | Glossary drift only |
| **Fix** | Alias table in `00b-glossary.md` |
| **Acceptance** | Capability validator + cert matrix use same names as docs |

### G-BS-P2-6 — Duplicate / overlapping contract test bases

| | |
|---|---|
| **Constitution** | Single contract test inheritance for all brokers |
| **As-built** | `BrokerContractSuite`, `MarketCoverageContract`, `GatewayContractSuite` (`tests/unit/brokers/common/test_gateway_contract_suite.py`), `BrokerAdapterContractSuite` — overlapping coverage |
| **Violation** | Maintenance burden; ambiguous "source of truth" suite |
| **Fix** | Deprecate `GatewayContractSuite`; consolidate into two bases (market + execution) |
| **Acceptance** | One documented canonical pair in `tests/README.md` |

---

## P3 — Lower priority

### G-BS-P3-1 — Legacy SPI protocols in `brokers/common/api/`

| | |
|---|---|
| **As-built** | `MarginProvider`, `MarketDataProvider`, etc. (`brokers/common/api/__init__.py`) parallel domain ports |
| **Fix** | Migrate callers to domain ports; delete SPI when unused |

### G-BS-P3-2 — `IRateLimiter` / `IInstrumentMapper` protocols absent

| | |
|---|---|
| **As-built** | Concrete `MultiBucketRateLimiter`; mapping via `BrokerInstrumentService` protocol (`brokers/common/instruments/service.py`) |
| **Fix** | Optional domain ports if test doubles need them |

### G-BS-P3-3 — Missing top-level test category directories

| | |
|---|---|
| **Constitution** | `tests/{property,contracts,sandbox,live,stress,resilience,performance,acceptance}/` |
| **As-built** | Markers + paths: `tests/unit/brokers/` (215 files), `tests/integration/brokers/` (63), `tests/component/brokers/` (2), `tests/performance/` (2, not broker-specific). No top-level `property/`, `stress/`, `resilience/`, `acceptance/` |
| **Fix** | Document marker-based pyramid in `tests/README.md`; add dirs only when suites grow |

### G-BS-P3-4 — Rate-limit cert is warn-only

| | |
|---|---|
| **Constitution** | "Rate limits enforced without broker-side throttling or HTTP 429 under normal operation" |
| **As-built** | `RATE_BURST` / `RATE_SUSTAINED` are `warn_only=True` in cert (`suite.py:130–131`); burst test runs 5 rapid quotes, no 429 assertion |
| **Fix** | Promote to hard fail for live brokers after baseline captured |
| **Acceptance** | Cert fails if 429 observed under declared `RateLimitProfile` |

---

## Quality gates checklist (spec → evidence)

| Gate | Status | Evidence |
|---|---|---|
| **Architecture compliance** (prescribed package structure) | ✅ Documented | Layered layout intentional; layout map §G-BS-P2-1 |
| **Contract compliance** (complete broker contract suite) | ✅ | `BrokerContractSuite` includes auth + order lifecycle; `MarketCoverageContract` |
| **Coverage** (high unit/component coverage) | ✅ Strong | `tests/unit/brokers/`; `tests/component/brokers/` |
| **Integration** (sandbox + live) | ✅ Framework | Marker-gated live probes + Upstox/Dhan regression manifests |
| **Performance** (latency/throughput budgets) | ⚠️ Soft | `brokers/diagnostics/benchmark.py`; `CertArea.QUOTE_LATENCY`; no CI perf gate |
| **Resilience** (auth/network/WS/rate-limit recovery) | ✅ Probes | Live probes for disconnect/reconnect/session recovery + subscription restore |
| **Certification** (real-market suite) | ✅ Code / ⚠️ Ops | Probes no longer stubbed; operator must run with live credentials |

**Production-ready verdict (per spec):** Paper broker — **ready** when composition wiring is present (certification conftest). Dhan/Upstox live — **code-ready**; production deployment still requires a green live certify run.

---

## Testing pyramid conformance

| Spec tier | As-built | Notes |
|---|---|---|
| Unit (offline) | ✅ `tests/unit/brokers/` | Rate limiter, mapping, parsers, state machines |
| Property | ❌ No top-level dir | Some round-trip tests in mapping cert |
| Contract | ✅ `brokers/common/contracts/` | Shared pytest bases |
| Component | ⚠️ `tests/component/brokers/` (2 files) | Session federation, instrument boundary |
| Sandbox | ⚠️ Marker-based | `scripts/debug/sandbox_order_smoke.py` |
| Integration | ✅ `tests/integration/brokers/` | Live + mock paths |
| Live market | ⚠️ `@pytest.mark.live_readonly`, `@pytest.mark.market_hours` | Not a separate directory |
| Acceptance | ⚠️ Partial | `tests/integration/brokers/certification/test_e2e_paper_trading_os.py` |
| Performance | ⚠️ `tests/performance/` (2 files) | Not broker-specific |
| Stress / Resilience | ❌ | No dedicated broker stress suite |

---

## Real-market certification criteria (detailed)

| Criterion | Verdict | Evidence |
|---|---|---|
| Login with valid token, no unnecessary regeneration | ✅ Probe | `probe_token_refresh` in `live_probes.py` |
| Expired token triggers auto-regeneration + persistence | ✅ Probe | `probe_token_expiry`; `TOKEN_EXPIRED`/`TOKEN_REFRESHED` published from auth paths |
| Instrument master → bidirectional mapping | ✅ | `brokers/certification/mapping.py` (6 asset classes); golden in `golden.py` |
| Historical ordered, gap-free | ✅ | `assert_gap_free_historical` in `_hist` |
| Live subscriptions → canonical events, accurate timestamps | ✅ Market-hours | `CertArea.LIVE_STREAM` + subscription restore in session recovery |
| Order lifecycle → canonical events | ✅ | Cert market/limit/cancel/modify + `BrokerContractSuite` lifecycle tests |
| Rate limits without 429 | ✅ Hard fail | `RATE_BURST` / `RATE_SUSTAINED` no longer `warn_only` |
| Reconnect restores session + subscriptions | ✅ | `probe_session_recovery` asserts FSM + resubscribe + LTP |
| Portfolio/positions/funds reconcile | ⚠️ Presence | Cert checks presence; deep OMS reconcile remains OMS-layer |
| Broker exceptions → canonical errors | ✅ | Dhan transport + Upstox order gateway mapped via `transport_errors` |
| Metrics/logs/traces for significant ops | ⚠️ Optional | Contract suite observability hooks; no OTel cert gate |

---

## Ranked backlog (broker subsystem only)

| Rank | Gap ID | Action | Type | Status |
|---|---|---|---|---|
| 1 | G-BS-P0-1 | Implement live cert probes (token, reconnect, recovery) | Integration | ✅ |
| 2 | G-BS-P0-2 | Transport error mapping ratchet | Contract | ✅ |
| 3 | G-BS-P0-3 | Unified session state aggregate | Redesign | ✅ |
| 4 | G-BS-P1-2 | Consolidate contract test inheritance | Test | ✅ |
| 5 | G-BS-P1-3 | Publish lifecycle events | Integration | ✅ |
| 6 | G-BS-P1-6 | Gap-free historical cert | Test | ✅ |
| 7 | G-BS-P2-1 | Layout map in docs (this file) | Docs | ✅ |
| 8 | G-BS-P3-3 | Test pyramid doc in `tests/README.md` | Docs | ✅ |

---

## Acceptance for broker gap analysis + remediation complete

- [x] Spec sections mapped to as-built locations with Exists / Partial / Missing
- [x] Architecture-fit finding documents layer-boundary conflict with monolithic spec
- [x] P0/P1/P2/P3 gaps with Constitution / As-built / Fix / Acceptance
- [x] Quality gates and certification criteria scored against evidence
- [x] Remediation Contexts 1–9 implemented; conformance tables refreshed post-remediation
- [ ] Operator: green live certify for Dhan and Upstox with credentials (ops gate)

---

## Addendum — 2026-07-21 broker + market-data remediation

| ID | Area | Verdict | Notes |
|---|---|---|---|
| G-BS-REM-P0-1 | Dhan subscription ownership | ✅ Closed | `DataProvider.stop_fn` → `unstream`; `SubscriptionEngine` ref-count fix |
| G-BS-REM-P0-2 | Dhan/Upstox read-path silent failures | ✅ Closed | `get_order`/`get_quote`/`get_depth` raise typed errors |
| G-BS-REM-P0-3 | Upstox modify_order integrity | ✅ Closed | Body parsing via `UpstoxDomainMapper`; instrument_key fallback removed |
| G-BS-REM-P0-4 | Live bar parquet hot path | ✅ Closed | Async `LiveBarSink` queue + `file_lock()` on merge-write |
| G-BS-REM-P0-5 | IST candle bucketing + gap inject | ✅ Closed | `CandleAggregator` IST alignment; `StreamOrchestrator.inject_reconciled_bars` |
| G-BS-REM-P1-1 | Dhan live-order guard parity | ✅ Closed | `convert_position`/`exit_all`/`cancel_all_orders` gated |
| G-BS-REM-P1-2 | Upstox lifecycle + capability wiring | ✅ Closed | `disconnect()` cascades WS; `PORTFOLIO_STREAM` target fixed |
| G-BS-REM-P1-3 | Single-broker StreamOrchestrator | ✅ Closed | `BrokerInfrastructure` wires with ≥1 broker |
| G-BS-REM-P1-4 | Account registry 401 storm | ✅ Closed | `AccountConnectionRegistry.record_auth_failure` invalidates cache |

---

## Addendum — 2026-07-21 review findings remediation (second pass)

| ID | Area | Verdict | Notes |
|---|---|---|---|
| G-BS-REV-P0-1 | Malformed order response → silent ok | ✅ Closed | Shared `order_result_from_response()` defaults `success=False` |
| G-BS-REV-P0-2 | Upstox subscribe raw dict leak | ✅ Closed | `UpstoxDataProvider._on_tick` normalizes via `_normalize_quote` |
| G-BS-REV-P0-3 | Dhan tick normalize swallow | ✅ Closed | WARNING log `tick_normalize_failed`; feed thread preserved |
| G-BS-REV-P1-1 | Dhan post-cancel fill race | ✅ Closed | `OrderCanceller._verify_cancel_not_race_filled` + `get_order_fn` |
| G-BS-REV-P1-2 | Paper limit fill parity | ✅ Closed | `PaperOrders.try_fill_on_quote` + `wire_paper_limit_fills` |
| G-BS-REV-P1-3 | Capabilities validator expansion | ✅ Closed | Core `supports_*` flags mapped; extensions excluded (ponytail) |
| G-BS-REV-P1-4 | Gateway TypeError fallback | ✅ Closed | Legacy fallback paper-only in `GatewayExecutionProvider` |
| G-BS-REV-P2-1 | Hardcoded IST SQL interval | ✅ Closed | `IST_SQL_INTERVAL` from `IST_OFFSET` in sync/normalize |

---

## Evidence references

| Path | Finding |
|---|---|
| `src/domain/ports/broker_adapter.py` | Canonical `BrokerAdapter` port |
| `src/domain/instruments/instrument_id.py` | Canonical instrument identity |
| `src/domain/capabilities/broker_capabilities.py` | Immutable capability matrix |
| `src/domain/errors.py` | Canonical error hierarchy |
| `src/domain/events/types.py:137–140` | Lifecycle event types (under-published) |
| `src/domain/stream_health.py` | Fragmented health FSMs |
| `src/infrastructure/resilience/rate_limiter.py` | Token-bucket rate limiting |
| `src/application/scheduling/quota_scheduler.py` | Global quota scheduler |
| `src/brokers/session/broker_session.py` | Public broker session facade |
| `src/brokers/common/contracts/broker_contract.py` | Shared market-data contract tests |
| `src/brokers/certification/suite.py` | Live cert stubs |
| `src/brokers/certification/mapping.py` | Six-asset-class mapping cert |
| `tests/integration/brokers/dhan/regression/manifest.py` | Dhan-only regression enforcement |
| `tests/unit/brokers/common/test_gateway_error_surface_contracts.py` | Cross-broker error regression guards |
| `context/architecture.md` §3 | Dependency rule — brokers are plugins, not owners of domain ports |
