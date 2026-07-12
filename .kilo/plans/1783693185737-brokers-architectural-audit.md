# Brokers Package — Architectural Audit & Refactoring Plan

**Scope:** `src/brokers` (`common`, `dhan`, `upstox`, `paper`)
**Date:** 2026-07-10
**Strategy (confirmed):** **Broker kernel + thin wire adapters, staged (strangler-fig).** Extract broker-*invariant* mechanism into `brokers/common`; reduce each broker to a thin *wire adapter* registered declaratively. New broker/exchange/feature = data + a small adapter, never a copy of the 200-file hierarchy.

**Also adopted — Market Surface Architecture (user-provided, verified against code).** This is the *concrete down-payment* on REF-3's "declarative capability data" and an extension of REF-0's contract. It is deliberately **domain-native** (adds `MarketSurface` + `BrokerCapabilities.market_surfaces`/`serves` to the existing `domain/capabilities` SSOT) rather than a new kernel class — we **reject** a separate `CapabilityEngine`/`MarketRegistry` (YAGNI). It also fixes the broken `brokers.*.tests.*` imports (CI blocker, 35 sites) and closes NSE/MCX/CDS coverage gaps via one parametrized `MarketCoverageContract` instead of per-broker MCX test files. It is low-risk and unblocks `pytest --collect-only`, so it runs **early (Stage 0.5)**, in parallel with the kernel foundation.

> The first-pass audit (this file's history) cataloged smells and proposed per-file "route through the existing seam" fixes. That treats symptoms. The durable disease is **one root cause**: there is no enforced port contract and no separation of *broker-invariant mechanism* from *broker-varying policy*, so every addition is hand-edited across a dozen files and two mirror gateways must be re-synced by hand. This plan fixes the root cause.

---

## PHASE 1 — Codebase Mapping (summary)

**Packages & responsibility**
- `common/` — thin shared utility layer (NOT a re-export facade; `__all__=[]`). Real modules: `backoff`, `idempotency`, `order_validation`, `tick_validation`, `api/{spi, protocols}`, `contracts/broker_contract`, `instruments/{carrier,keys,service}`, `oms/margin_provider`.
- `dhan/` — full transport: `api`, `auth`, `config`, `data`, `domain`, `execution`, `extensions`, `identity`, `instruments`, `portfolio`, `resilience`, `streaming`, `websocket` (~90 files).
- `upstox/` — full transport: `adapters`, `auth`, `capabilities`, `config`, `data`, `extensions`, `fundamentals`, `instruments`, `ipo`, `kill_switch`, `mappers`, `market_data`, `market_intelligence`, `mutual_funds`, `news`, `orders`, `payments`, `reconciliation`, `static_ip`, `websocket` (~120 files).
- `paper/` — in-memory sim broker; `PaperGateway` mirrors the gateway surface via `PaperDataProvider`/`PaperExecutionProvider` to `domain.ports`.

**Dependency direction (verified)**
- Outbound boundary is **clean**: `domain`/`tradex`/`analytics` import only `domain.ports.*` — zero deep `brokers.<x>.*` imports. ✅
- Inbound adoption of `common` is **selective & inconsistent**: both brokers use `idempotency/order_validation/tick_validation/broker_capabilities`; **upstox ignores `common.backoff` and `domain.constants.resilience`**.
- Ports live in `domain`, not `common`: `domain/ports/broker_adapter.py` (`BrokerAdapter = DataProvider + ExecutionProvider`), `domain/ports/protocols.py`, `domain/capabilities/*`. `common/api/spi.py` holds only `BrokerSource`.
- Intra-package hub: `dhan/streaming/connection.py` depends on ~20 sibling modules.

**Seams that already exist (and are under-used):** `domain/enums` (OrderType/ProductType/Side/Validity — used ✅), `domain/status_mapper` (used ✅ but bypassed at write sites), `domain.value_objects.price.to_wire_float` (used ✅ but ~260 raw `Decimal(str())` sites remain), `domain/constants/exchanges.py` (**exists, imported by NEITHER broker**), `domain/constants/resilience` (dhan only), `common/backoff` (dhan only), `common/contracts/broker_contract.py` (conformance suite).

---

## PHASE 2 — Root-Cause-First Findings

Each finding: **[SMELL-N] Pattern · Why the current design is insufficient · Evidence (file:line) · Blast radius · Impact.**

**[SMELL-1/2/3/4] A — Scattered constants (exchange codes, capability frozensets, `_NSE_SEGMENTS`, segment maps)**
- *Why insufficient:* capability/exchange vocabulary is **built imperatively in code** in ≥4 places per broker (`dhan/config/capabilities.py:135-136`, `upstox/capabilities/snapshot.py:152-153`, `upstox/instrument_adapter.py:99-123`, `upstox/instruments/segment_mapper.py:59-67`, `upstox/mappers/_base.py:42-62,134-141`, `dhan/segments.py:30-65`, `dhan/extensions/depth20.py:29`, `dhan/extensions/depth200.py:27`, `upstox/extensions/depth.py:29`, `dhan/domain.py:44-53`). Canonical `domain/constants/exchanges.py` exists but is imported **nowhere**. Adding an exchange = edit a dozen files. Root cause = **no declarative capability data + no single wire-map**.
- Blast radius: 12+ files. Impact: HIGH.

**[SMELL-5/6/18] B — Backoff/reconnect duplicated & divergent**
- *Why insufficient:* the WebSocket reconnect **loop** is written per broker with inline policy. dhan has 2 live loops (`websocket/connection.py:209-351`, `data/depth_feed_base.py:404-419` — the latter re-implements backoff despite importing `ReconnectingServiceMixin` it doesn't call) + `api/reconnecting_service.py` mixin + `resilience/retry_executor.py` + `config/config.py:123-132`. upstox has `websocket/v3_auto_reconnect.py:39` + `auth/http.py:414` + `auth/config.py` and **never imports `common.backoff`**. Constants diverge: upstox `ws_reconnect_max_retries` defaults to **5** (`auth/config.py:65-66`) vs **50** (`v3_auto_reconnect.py:17`). Root cause = **reconnect is mechanism, not policy; it belongs in one place with policy injected**.
- Blast radius: 3-7 files. Impact: HIGH.

**[SMELL-8/17/22] B/G — Raw dict leakage & status bypass**
- *Why insufficient:* adapters return raw `{"data":...}` / `dict` (`upstox/orders/order_query_adapter.py:21-31`, `gtt_client.py`, `tick_translator.py:65,82` returns raw dict on failure). Status normalization is **bypassed at write sites**: `dhan/execution/super_orders.py:340,361`, `forever_orders.py:309` inject raw `orderStatus` strings; upstox `gtt/cover/slice` adapters build `Order` with no status. Enabling type leak: `dhan/domain.py:198,218,252` types `order_status` as `str`. Facades reach into **private** infra (`upstox/gateway.py:244-256` reads `_read_circuit_breaker`, `token_manager.refresh_count`; `dhan/extended.py:317` raw `client.post(...)`). Root cause = **no boundary forces translation; the domain model does not forbid raw strings**.
- Blast radius: 8 files. Impact: HIGH.

**[SMELL-9] B — Margin parsing ×3**
- *Why insufficient:* `common/oms/margin_provider._parse_margin_response`, `dhan/portfolio/margin.py:80`, upstox `market_data/margin.py`/`margin_adapter.py` each normalize `totalMargin`/`orderMargin`/`spanMargin`/`exposureMargin`. dhan's `MarginAdapter` does **not** implement `MarginProvider` (upstox's does). Root cause = **no shared response normalizer behind the port**.
- Blast radius: 4 files. Impact: MEDIUM.

**[SMELL-10] B — Token lifecycle trees**
- *Why insufficient:* `auth/token_manager.py` + `token_scheduler.py` + `connection_token_manager.py` (dhan) vs `auth/token_manager.py` + `token_expiry.py` + `totp_scheduler.py` + `totp_client.py` + `pkce.py` + `oauth_client.py` + 5 holder classes + 2 state stores (upstox). Same folder, independent impls. Root cause = **token lifecycle is invariant mechanism expressed per broker**.
- Blast radius: 6-10 files. Impact: MEDIUM.

**[SMELL-11/16] C/F — Mirror gateways & adapter god-objects**
- *Why insufficient:* `DhanBrokerGateway` (`dhan/gateway.py:27`) and `UpstoxBrokerGateway` (`upstox/gateway.py:57`) expose near-identical hand-maintained surfaces; `UpstoxBroker` (`broker.py:78`) is a ~30-collaborator wiring god-object; `dhan/streaming/connection.py:11-118` wires ~20 siblings. Parallel `*Adapter` pairs (`PortfolioAdapter`, `MarketDataAdapter`/`MarketDataGateway`, `OrdersAdapter`/`OrderGateway`); upstox even has **two `PortfolioAdapter` classes** returning slightly different shapes. Root cause = **no single port contract + no use-case layer**, so "feature" = hand-wired across gateway+extended+extensions+adapter+client.
- Blast radius: 2+ per method. Impact: HIGH.

**[SMELL-12] D — `extended.py` name collision, opposite contents**
- *Why insufficient:* `dhan/extended.py` (derivatives chains) ≠ `upstox/extended.py` (IPO/news/fundamentals). Duplicate class names `DhanSuperOrderExtension`/`DhanForeverOrderExtension` exist twice each (`extensions/*` vs `extensions/common_extensions.py`). Root cause = **no naming convention separating plugin surface from registry**, and module name overloaded.
- Blast radius: 2-5 files. Impact: MEDIUM.

**[SMELL-13] D — Phantom `common` documentation**
- *Why insufficient:* 12+ docstrings reference gutted `brokers.common.core.*` / `brokers.common.lifecycle.*` / `brokers.common.adapters` etc. (e.g. `dhan/gateway.py:316`, `upstox/common_extensions.py:157`, `interface/ui/commands/certify.py:25`). Misleads every future refactor. Root cause = **docs rotted when `common` was split into `domain`/`infrastructure`/`application`**.
- Blast radius: 12 files (docs). Impact: MEDIUM.

**[SMELL-14/15] E — Fragmented feature ownership**
- *Why insufficient:* super/forever orders split across `execution/*` + `extensions/*` + `extensions/common_extensions.py` + `extended.py` + `streaming/connection.py` (5 files, duplicate class names) in dhan; GTT triple-implemented in upstox (`gtt_adapter` + `extended` + `common_extensions` stub `success=False`). upstox `broker.py:399` references undefined `self.exit_all` (latent bug). Root cause = **feature orchestration lives inside transport, not in a broker-agnostic use-case layer**.
- Blast radius: 5-6 files/feature. Impact: HIGH.

**[SMELL-19] G — Paper re-implements OMS**
- *Why insufficient:* `paper/paper_orders.py:_place_internal` (243-354) re-implements order/position state that `application.oms` already owns; synthetic fills bypass `common.order_validation`; paper never calls `common.idempotency` and implements neither `MarginProvider` nor the shared validators. Root cause = **OMS is broker-scoped, not shared**.
- Blast radius: 3 files. Impact: MEDIUM.

**[SMELL-20] F — dhan subpackage sprawl**
- *Why insufficient:* resolver in 3 places (`resolver.py`/`instruments/service.py`/`identity/identity.py`); `loader.py`↔`instruments/service.py`; `symbol_validator.py`↔`execution/order_validator.py`; `streaming/connection.py` vs `websocket/connection.py` (same filename); `data/depth_feed_base.py` is a WS impl in `data/`; `config/` 6 files, 3 re-bind `Dhan.REST_BASE`. Root cause = **premature file splitting without a unifying module boundary**.
- Blast radius: 2-3 files each. Impact: MEDIUM.

**[SMELL-21] H — `UpstoxBroker.capabilities` vs `UpstoxBrokerGateway.capabilities`**
- *Why insufficient:* two capability shapes for one broker (`broker.py:359` `_UpstoxCapabilities` dataclass vs `gateway.py:213` `BrokerCapabilities`); gateway reaches adapter internals. Root cause = **capability computed in the facade instead of declared as data**.
- Blast radius: 2 + consumers. Impact: MEDIUM.

---

## PHASE 3 — Root Cause Classification

1. **No enforced port contract** → SMELL-11/16/21 (mirror gateways, god-objects, capability divergence). Fix: formalize `domain.ports.BrokerAdapter` as the *only* contract; kernel owns conformance.
2. **No separation of invariant mechanism from broker-varying policy** → SMELL-5/6/10/18 (reconnect, backoff, token lifecycle written per broker). Fix: kernel `ReconnectingTransport` + `ResiliencePolicy` + `TokenLifecycle` service, policy injected.
3. **No declarative capability/exchange vocabulary** → SMELL-1/2/3/4. Fix: `CapabilityEngine` data table + per-broker `BrokerWireAdapter` wire maps.
4. **No anti-corruption boundary** → SMELL-8/17/22. Fix: mandatory `BrokerTranslator` ACL at the port edge; typed `OrderStatus` becomes unviolatable.
5. **OMS scoped to the broker** → SMELL-19. Fix: OMS in `application.oms`; paper is a transport + in-memory state store.
6. **Feature orchestration inside transport** → SMELL-14/15. Fix: broker-agnostic use-case layer + per-broker strategy.
7. **Premature file splitting / naming chaos / doc rot** → SMELL-12/13/20. Fix: registry + naming convention + doc sweep.

---

## PHASE 4 — Ideal Architecture & Refactoring Plan

### 4.0 Ideal Target Architecture

```
domain.ports.BrokerAdapter (= DataProvider + ExecutionProvider)   ← STABLE CONTRACT (exists)
        ▲
brokers/common/  ── THE KERNEL (broker-invariant) ──
   transport.py        ReconnectingTransport  (ONE ws/http lifecycle; ResiliencePolicy injected)
   resilience.py        ResiliencePolicy (data: backoff, max_attempts, staleness, refresh_buffer)
   acl.py               BrokerTranslator protocol  (EVERY broker output → domain entity; status normalized here)
   capabilities.py      thin re-export of domain.capabilities; the DECLARATIVE data lives on
                        BrokerCapabilities.market_surfaces (SSOT) + per-broker capability factories + wire maps
   margin.py            MarginProvider adapter + ONE response normalizer
   idempotency/order_validation/tick_validation/price.py   (promoted to the normalization boundary)
   contracts/           BrokerContractSuite (conformance, runs on ALL 3 brokers)
   registry.py          BrokerRegistry: register("dhan", wire=..., auth=..., capabilities=...)
        ▲
brokers/<x>/  ── THIN WIRE ADAPTER (broker-varying policy only) ──
   wire.py              BrokerWireAdapter: endpoints, status_map, field_mappings, price_decoder (declarative)
   auth.py              token lifecycle specifics (OAuth/TOTP) against kernel TokenLifecycle
   (NO reconnect loop, NO backoff, NO status normalization, NO capability frozensets, NO dup adapters)
        ▲
use-cases/  ── FEATURE LAYER (broker-agnostic) ──
   place_bracket.py, exit_all.py, gtt.py ...  orchestrate via port + per-broker strategy
```

**Extensibility guarantees this delivers**
- New broker = implement `BrokerWireAdapter` + one capability row + `register(...)`. No copy of the dhan/upstox skeleton. (SMELL-11/16)
- New exchange = add a row to `BrokerCapabilities.market_surfaces` + a wire map entry. (SMELL-1/2/3/4)
- New feature = add a use case + per-broker strategy; existing code untouched. (SMELL-14/15)
- New resilience rule = change `ResiliencePolicy` defaults; both brokers inherit. (SMELL-5/6/18)

**Trade-offs (justified)**
- Larger upfront extraction, but each stage is independently shippable (strangler-fig): gateways keep working via an adapter shim during migration; mirrors deleted only after the kernel serves the broker.
- The kernel's generic `ReconnectingTransport` must serve both dhan's binary depth feed and upstox's protobuf feed → **feed decoding lives in `BrokerWireAdapter`, kernel owns lifecycle only**. This is the key seam that keeps the kernel broker-agnostic.
- The object-centric `Instrument` model (OBJECT_MODEL_PLAN.md, superseded) is complementary: kernel emits domain entities the object layer wraps. Gateways become transports; no conflict.
- Risk: generic transport must not over-abstract edge cases. Mitigation: migrate dhan first (binary feed), prove the seam, then upstox (protobuf).

### 4.1 Staged, Dependency-Ordered Plan

Each task: **Root cause · Action · From · To · Touches · Test (behavior/contract) · Sequencing.**

**Stage 0 — Formalize the contract**
- **REF-0** Root cause 1. Action: Treat `domain.ports.BrokerAdapter` as the sole contract; extend `common/contracts/broker_contract.py` `BrokerContractSuite` to assert (a) typed returns, (b) `Order.order_status` is always `OrderStatus`, (c) capability parity. Run it against dhan + upstox + paper today (paper currently not enrolled). From: `domain/ports/broker_adapter.py`, `common/contracts/broker_contract.py`. To: same + paper enrollment. Touches: contract suite + 3 gateways. Test: suite green on all 3. Sequencing: none.

**Stage 0.5 — Market Surface + test repair (early, unblocks CI; runs in parallel with Stage 0/REF-3)**
- **REF-0.5** Root cause 7 (CI blocker, verified). *Ideal:* a single fixture home under `tests/support/brokers/{dhan,upstox}/`; all test imports use `tests.*`; no fixtures under `src/brokers`. *Action:* create `tests/support/brokers/dhan/fixtures.py` with deduplicated `SAMPLE_ROWS` + `FakeHttpClient` (currently duplicated in `tests/unit/brokers/dhan/test_edge_cases.py` + `test_chaos.py`); rewrite **all 35** broken imports: `brokers.dhan.tests.conftest` → `tests.support.brokers.dhan.*` / `tests.integration.brokers.dhan.*`; `brokers.upstox.tests.integration.conftest` → `tests.integration.brokers.upstox.conftest`; also `brokers.upstox.tests.unit.test_websocket_safety` (`tests/integration/test_upstox_portfolio_oms.py:13`) and `brokers.dhan.tests.unit.test_depth_feeds` (`test_recent_fixes.py:151`) and `brokers.dhan.tests.regression.manifest` (`test_live_read_surface_suite.py:30`, `test_coverage_manifest.py:14`). Verify `pytest --collect-only` on the affected trees. From: 35 import sites across `tests/unit/brokers/dhan`, `tests/integration/brokers/{dhan,upstox}`, `tests/integration/test_upstox_*.py`. To: `tests/support/brokers/*` + existing `tests/.../conftest.py`. Touches: ~20 test files. Test: `pytest --collect-only` succeeds on `tests/integration/brokers/{dhan,upstox}` + `tests/unit/brokers/dhan`. Sequencing: none (do first — unblocks all later test runs).
- **REF-0b** Root cause 3 (coverage gaps). *Ideal:* one parametrized `MarketCoverageContract` driven by `caps.market_surfaces` — guarantees every declared surface has ≥1 behavioral assertion, and adding a broker needs zero new matrix code (no broker-name branches). *Action:* extend `common/contracts/broker_contract.py` (or add `MarketCoverageContract`): offline — surfaces with `resolve` resolve via instrument service with no wire-ID leak on the domain `Quote`; live (`live_readonly`) — for each `surface × operation`, call the gateway/session and assert domain invariants (ltp>0 or non-empty chain; skip only on empty off-hours / rate-limit with explicit reason). Broker-specific live files keep deep cases; this suite does not duplicate them. From: `common/contracts/broker_contract.py`, the per-broker `test_live_*` files. To: `MarketCoverageContract`. Touches: contract suite + 2 brokers. Test: each declared surface (incl. MCX futures both brokers, Dhan MCX options, CDS spot) has a contract assertion; live skips cleanly when no creds. Sequencing: after REF-3b (needs populated surfaces) + REF-0.5.
- **REF-3c** (see Stage 1, `Universe.spot` → `CDS`) also belongs here conceptually; keep with REF-3.

**Stage 1 — Kernel invariants (the mechanism extraction)**
- **REF-1** Root cause 2. *Ideal:* one `ReconnectingTransport` + injected `ResiliencePolicy`; policy defaults centralized in `domain/constants/resilience.py` (fix the 5-vs-50 mismatch). *Action:* add `common/transport.py` (`ReconnectingTransport`) + `common/resilience.py` (`ResiliencePolicy`); delete upstox `v3_auto_reconnect.next_delay` + `auth/http._backoff`; make dhan `depth_feed_base.py` actually use the mixin it imports; retire dhan `RetryConfig.calculate_backoff` if redundant. From: `dhan/websocket/connection.py`, `dhan/data/depth_feed_base.py`, `dhan/api/reconnecting_service.py`, `upstox/websocket/v3_auto_reconnect.py`, `upstox/auth/http.py`, `upstox/auth/config.py`, `upstox/auth/token_manager.py`, `upstox/totp_scheduler.py`. To: `common/transport.py`, `common/resilience.py`, `domain/constants/resilience.py`. Touches: SMELL-5/6/18 (~8 files). Test: unit test backoff sequence identical for both brokers; injected `ResiliencePolicy` drives reconnect in integration drop-simulation. Sequencing: after REF-0.
- **REF-2** Root cause 4. *Ideal:* mandatory `BrokerTranslator` ACL — every broker output passes through ONE translator to a domain entity; `OrderStatus` normalized here; raw dicts cannot escape. *Action:* add `common/acl.py` (`BrokerTranslator` protocol + base impl); wrap `upstox/order_query_adapter`, `gtt_client`, `tick_translator` (return `Quote`, raise on failure instead of raw dict), `dhan/extended.py:317` raw post; ban private-attr reaches in `upstox/gateway.py:244-256`; change `dhan/domain.py` `order_status: str` → `OrderStatus`. From: `dhan/domain.py:198-252`, `dhan/execution/super_orders.py`, `forever_orders.py`, `upstox/orders/{gtt,cover,slice}_adapter.py`, `upstox/tick_translator.py`, `upstox/data_provider.py`, `upstox/gateway.py`, `dhan/extended.py`. To: `common/acl.py` + typed field. Touches: SMELL-8/17/22 (~8 files). Test: contract suite asserts `Order.order_status` always enum and no `dict` return; mypy strict on `brokers/<x>/adapters`. Sequencing: after REF-0.
- **REF-3** Root cause 3. *Ideal (reconciled with Market Surface Architecture):* capability/exchange/asset vocabulary is **declarative data on `BrokerCapabilities`**, the existing SSOT — NOT a new kernel class. Add `MarketSurface` (`asset_kind × exchange × probe_symbol × operations`) + `BrokerCapabilities.market_surfaces`/`serves()` to `domain/capabilities/broker_capabilities.py`; keep `exchange` values from the centralized `domain/constants/exchanges.py` (currently unused). Wire maps stay in `BrokerWireAdapter`.
  - **REF-3a** *Action:* add `src/domain/capabilities/market_surface.py` (`MarketSurface` frozen dataclass + `AssetKind`); extend `BrokerCapabilities` with `market_surfaces: frozenset[MarketSurface]` + `serves(asset_kind, exchange) -> bool`. Unit tests for the value object + `serves` query. From: `src/domain/capabilities/broker_capabilities.py`. To: `src/domain/capabilities/market_surface.py` + extended `BrokerCapabilities`. Touches: SMELL-1 (2 files). Test: unit — `serves()` matrix; frozen-equality.
  - **REF-3b** *Action:* populate `dhan_capabilities()` (`src/brokers/dhan/config/capabilities.py`) and Upstox snapshot (`src/brokers/upstox/capabilities/snapshot.py`) with NSE/NFO/MCX/CDS surfaces (EQUITY@NSE RELIANCE; OPTIONS/FUTURES@NFO NIFTY; FUTURES@MCX GOLD; OPTIONS@MCX GOLD for Dhan; SPOT@CDS USDINR). Also delete the duplicated capability frozensets (SMELL-2) and the three `_NSE_SEGMENTS` copies (SMELL-3) and the parallel segment maps (SMELL-4) now that `domain/constants/exchanges.py` + `market_surfaces` own them. From: `dhan/config/capabilities.py:135-136`, `upstox/capabilities/snapshot.py:152-153`, `dhan/segments.py`, `dhan/domain.py` `Exchange` enum, `upstox/instrument_adapter.py`/`segment_mapper.py`/`mappers/_base.py` segment funcs, `dhan/extensions/depth20.py:29`, `dhan/extensions/depth200.py:27`, `upstox/extensions/depth.py:29`. To: capability factories + `domain/constants/exchanges.py`. Touches: SMELL-1/2/3/4 (~12 files). Test: assert dhan & upstox `market_surfaces` cover the declared lanes; grep ban on bare exchange literals; `serves()` parity.
  - **REF-3c** *Action (domain default fix):* `Universe.spot` (`src/domain/universe.py:130`) defaults `exchange="NSE"` — wrong for FX spot; `exchange_segments.py:46` maps `CDS→NSE_CURRENCY`. Change default to `CDS`; cover in an asset-kind/universe unit test. From: `src/domain/universe.py:130`. To: `exchange="CDS"`. Touches: SMELL-1 (1 file). Test: domain test that `Universe.spot("USDINR").exchange == "CDS"`.
  *Sequencing:* REF-3a before REF-3b; REF-3 can start in **Stage 0.5** (parallel with REF-0) because it only touches capability data + domain, unblocks nothing risky, and feeds REF-0b.
- **REF-4** Root cause (margin). *Ideal:* one `MarginProvider` adapter + one response normalizer behind the port. *Action:* make `dhan/portfolio/margin.py` implement `common/api.MarginProvider` (like upstox); route both through `common/oms/margin_provider.BrokerMarginProvider`; delete duplicated `_parse_margin_response`. From: `dhan/portfolio/margin.py`, `common/oms/margin_provider.py`, `upstox/market_data/margin*.py`. To: `MarginProvider` port. Touches: SMELL-9 (4). Test: margin contract test; numeric parity on sample response. Sequencing: after REF-2.
- **REF-5** Root cause 2 (token). *Ideal:* `TokenLifecycle` service in kernel; per-broker `auth.py` supplies only OAuth/TOTP specifics. *Action:* extract shared token refresh/proactive-refresh/401-retry/state-store from dhan & upstox `auth/token_manager*.py` into `common/auth/`; brokers keep only wire-specific auth. From: `dhan/auth/*`, `upstox/auth/token_manager.py`, `token_expiry.py`, `totp_scheduler.py`, `holders.py`, `*_state_store.py`. To: `common/auth/TokenLifecycle` + thin per-broker auth. Touches: SMELL-10 (~10). Test: token-refresh integration (mock 401 → refresh → retry succeeds); proactive refresh before expiry. Sequencing: after REF-1.

**Stage 2 — Feature/use-case layer**
- **REF-6** Root cause 6. *Ideal:* broker-agnostic use cases (`place_bracket`, `exit_all`, `gtt`, `pnl_exit`, `depth`) orchestrate via the port + a per-broker *strategy* for wire specifics. *Action:* create `brokers/common/usecases/` (or `application/`): each use case depends on `BrokerAdapter` + `BrokerWireAdapter.strategy_for(feature)`. Migrate dhan super/forever/exit-all/pnl-exit and upstox GTT/exit-all into use cases; delete the duplicate `Provider` classes in `extensions/common_extensions.py` (rename to avoid the `Dhan*Extension` name collision). Fix latent bug `upstox/broker.py:399` `self.exit_all`. From: SMELL-14/15 files (~12). To: `usecases/` + per-broker strategy. Touches: ~12. Test: use-case contract tests (place/cancel super, GTT, exit-all) per broker; behavior-focused. Sequencing: after REF-2, REF-3.

**Stage 3 — Migrate dhan behind the kernel (thin wire adapter)**
- **REF-7** Root cause 1/7. *Action:* implement `dhan/wire.py` (`BrokerWireAdapter`: endpoints, status_map, field maps, price decoder, feed decoder) + `dhan/auth.py`; register via `BrokerRegistry`. Collapse `dhan/extended.py` (derivatives) into use cases; fold `resolver.py`/`loader.py`→`instruments/service.py`; merge `symbol_validator.py`→`execution/order_validator.py`; move `data/depth_feed_base.py`→`websocket/`; rename `streaming/connection.py`→`streaming/session.py`. Keep `dhan/gateway.py` as a thin transport shim during migration, delete after Stage 4 proves parity. From: SMELL-12/20 files (~10). To: `dhan/wire.py` + registry. Touches: ~10. Test: `BrokerContractSuite` green via dhan wire adapter. Sequencing: after REF-1..6.

**Stage 4 — Migrate upstox behind the kernel; delete mirrors**
- **REF-8** Root cause 1/7. *Action:* implement `upstox/wire.py` + `upstox/auth.py`; register. Delete the **two `PortfolioAdapter` classes** (merge to one `PortfolioProvider`); stop `MarketDataGateway` double-wrapping `UpstoxMarketDataAdapter`; collapse `upstox/extended.py` (rename to `extras.py` to resolve the `extended.py` non-parity with dhan, or document non-parity per ADR); unify `UpstoxBroker.capabilities` with `UpstoxBrokerGateway.capabilities` (single builder, REF-21).
  - **REF-8b** (manifest boundary): `tests/integration/brokers/dhan/regression/manifest.py` is a Dhan-private second capability list. Thin it — MCX/CDS lanes migrate to the shared `MarketCoverageContract` (REF-0b); the manifest keeps only Dhan-specific quirks (depth-200 single-instrument, forever orders). Stop adding NSE-parity rows there. From: `tests/integration/brokers/dhan/regression/manifest.py`. To: trimmed manifest + shared contract owns P0 lanes. Touches: 1 file. Test: `pytest --collect-only` + coverage contract asserts MCX/CDS without manifest duplication. From: SMELL-11/12/16/21 files (~8). To: `upstox/wire.py` + registry. Touches: ~8. Test: contract suite green; capability parity assertion. Sequencing: after REF-7.

**Stage 5 — Paper as kernel consumer**
- **REF-9** Root cause 5. *Action:* move OMS into `application.oms` (broker-agnostic); `paper` becomes a transport + in-memory state store behind the same `BrokerAdapter`; `PaperGateway` declares `BrokerAdapter`; enroll in `BrokerContractSuite`; route paper through `common.idempotency`/`order_validation`/`tick_validation`; implement `MarginProvider` (trivial) or document intentional omission per ADR. From: `paper/paper_orders.py` (`_place_internal`), `paper/paper_portfolio.py`. To: `application.oms` + thin paper transport. Touches: SMELL-19 (3). Test: contract suite for PaperGateway; parity test vs dhan/upstox. Sequencing: after REF-2, REF-4.

**Stage 6 — Guardrails & doc hygiene**
- **REF-10** Root cause 7. *Action:* sweep 12+ phantom `brokers.common.*` docstrings → repoint to `domain`/`infrastructure`/`application`; implement or fix `interface/ui/commands/certify.py:25` `certify_broker`. From: SMELL-13 (~12). To: corrected docs. Test: grep ban on `brokers.common.core.*`/`brokers.common.lifecycle.*`. Sequencing: parallel, anytime.
- **REF-11** Root cause 1/7. *Action:* add `__all__` to every broker public module; add `import-linter` layer rules forbidding `domain`/`tradex` → `brokers.<x>.<deep>`, and `gateway.*._*` private reaches; wire mypy strict + pre-commit grep (ban bare exchange literals, `body.get("data")`) into CI. From: all `__init__.py` + CI. To: lint config. Test: lint passes in CI. Sequencing: after REF-8 (boundary stable).

---

## PHASE 5 — Structural Recommendations

### 5.1 Proposed Directory Structure (target)
```
src/brokers/
  common/                         # KERNEL: broker-invariant
    transport.py  resilience.py  acl.py  capabilities.py  registry.py
    auth/TokenLifecycle.py
    margin.py  idempotency.py  order_validation.py  tick_validation.py  price.py
    usecases/                     # broker-agnostic feature orchestration
    contracts/broker_contract.py  # conformance (all 3 brokers)
    instruments/{carrier,keys,service}.py
  dhan/  upstox/                  # THIN WIRE ADAPTERS
    wire.py        # BrokerWireAdapter: endpoints, status_map, field/price/feed decoders (declarative)
    auth.py        # OAuth/TOTP specifics only
    (NO reconnect loop / backoff / status norm / capability frozensets / dup adapters)
  paper/                          # transport + in-memory state store
```
Drop: `common/broker_capabilities.py` (shim), dhan top-level `resolver/loader/symbol_validator/extended`, upstox dual `PortfolioAdapter`, `extended.py`→`extras.py`.

### 5.2 Boundary Rules (enforced by import-linter)
1. `domain`/`tradex` import **only** `domain.ports.*` — never `brokers.<x>.*` submodules. (locked)
2. The kernel (`common`) depends on `domain` only; never on a specific broker.
3. A broker package depends on `common` (kernel) + `domain`; never on another broker.
4. Adapters return **typed domain entities**; raw `dict`/`{"data":...}` never crosses the `acl.py` boundary.
5. `Order.order_status` is **always** `OrderStatus` (normalized in `acl.py`).
6. Reconnect/resilience constants live **only** in `domain/constants/*` + kernel `ResiliencePolicy`; exchange/segment/asset-coverage vocabulary lives **only** on `BrokerCapabilities.market_surfaces` (SSOT) + `domain/constants/exchanges.py`. No per-file capability frozensets.
7. `mappers/` = wire→domain converters; `usecases/` = feature orchestration; `wire.py` = declarative broker policy. One meaning per name.
8. **`market_surfaces` is the single source of truth for asset/exchange coverage** — shared contracts iterate it; no broker-name (`if broker=="dhan"`) branches in `domain` or shared contracts.

### 5.3 Coding Standards (checkable)
1. Exchange/segment codes ONLY from `domain/constants/exchanges.py` — grep ban on bare `"NSE"/"NFO"/"MCX"` in `brokers/`.
2. Prices ONLY via `price.py`/`BrokerWireAdapter.price_decoder` — ban raw `Decimal(str(payload[...]))` in adapters.
3. Status ONLY via `OrderStatus.normalize` in `acl.py` — no raw broker status strings assigned to `order_status`.
4. Reconnect/backoff ONLY via kernel `ReconnectingTransport` + `ResiliencePolicy` — ban inline `** attempt` loops.
5. Capabilities declared ONCE as data on `BrokerCapabilities.market_surfaces` — no per-file `frozenset({"MARKET",...})`, no `if broker==` branches in shared code.
6. Public adapter methods return typed entities (mypy strict on `brokers/<x>/{wire,adapters}`).
7. No duplicate class names within a package; `Extension` (plugin) vs `Strategy` (registry) naming must not collide.
8. Every public module declares `__all__`; collaborators are `_private` and not imported cross-package.

### 5.4 Guardrails
- **import-linter** `forbidden` layers: `domain`→`brokers.<x>.<deep>`; `gateway`→`gateway._*` internals. In CI.
- **BrokerContractSuite** runs on dhan + upstox + paper every PR — guarantees facade parity + typed returns + `OrderStatus` always enum.
- **mypy/pyright strict** on `brokers/` returns + `OrderStatus` field — catches SMELL-8/17 regressions.
- **ADR template** for any new broker/feature: must declare (a) which use case owns it, (b) which `domain` port it satisfies, (c) where its constants/policy live. Reject PRs adding a new frozenset/backoff loop/raw-dict return.
- **Pre-commit grep hook** banning bare exchange literals + `body.get("data")` in `brokers/<x>/adapters`.
- **Module `__all__`** + `ruff` `unused`/`redefined` to catch duplicate names (SMELL-12) + dead shims.
- **graphify update**: run `graphify update .` after all code changes so the dependency map reflects the new kernel/wire-adapter boundaries (per repo convention).

---

## What we will NOT do
- **Not** add standalone `test_live_mcx_upstox.py` without the surface declaration (symptom fix) — coverage comes from `MarketCoverageContract` over `market_surfaces`.
- **Not** grow Dhan `manifest.py` with MCX rows as the primary fix — MCX/CDS lanes live in the shared contract.
- **Not** invent a new `MarketRegistry` / `CapabilityEngine` class — `BrokerCapabilities.market_surfaces` is the SSOT (YAGNI).
- **Not** mock live market data — live lanes use real credentials and skip when absent (existing project rule).
- **Not** add broker-name branches (`if broker=="dhan"`) in `domain` or shared contracts — coverage is data-driven.
- **Not** edit this audit plan file (per Market Surface brief).

---

## Validation Summary
- **Unit:** backoff sequence parity, price paise↔rupee, status normalization, `MarketSurface`/`serves()` matrix, `Universe.spot` default `CDS`, token 401→refresh→retry.
- **Contract:** `BrokerContractSuite` + `MarketCoverageContract` over dhan + upstox + paper (typed returns, `OrderStatus` enum, `market_surfaces` coverage incl. MCX futures both brokers, Dhan MCX options, CDS spot; live skips cleanly without creds).
- **CI unblock:** `pytest --collect-only` on `tests/integration/brokers/{dhan,upstox}` + `tests/unit/brokers/dhan` no longer fails on missing `brokers.*.tests` modules (REF-0.5).
- **Type:** mypy strict on `brokers/`.
- **Lint:** import-linter layers + grep hooks in CI.
- **Integration:** place/cancel super order, GTT/forever, exit-all, depth-20/200, reconnect drop simulation, `MarketCoverageContract` live walk via `tradex.connect(..., load_instruments=True)`, new-broker registration smoke (add a stub 4th broker via `register` to prove zero existing-code edit).

## Open Questions / Domain-Knowledge Flags
- **NSE margin fields:** `common/oms/margin_provider._parse_margin_response` `spanMargin`/`exposureMargin` — confirm authoritative fields per exchange before merging dhan margin (flagged, not guessed).
- **upstox `ws_reconnect_max_retries` 5 vs 50:** product-owner decision on intended default (REF-1).
- **`extended.py` non-parity:** confirm rename upstox→`extras.py` is acceptable to callers (REF-8).
- **Paper `MarginProvider`:** confirm sim margin in-scope or intentionally omitted (REF-9).
- **Object model:** confirm kernel's domain entities are the ones the `Instrument`/`Session` object layer (OBJECT_MODEL_PLAN) wraps, so we don't build a second object model.
- **Dhan MCX options support:** confirm Upstox API supports OPTIONS@MCX before declaring that surface for Upstox (REF-3b probe table).

---

## Status log (2026-07-11 — kernel strangler execution)

- REF-0/0.5/0b/3: **Done** — `BrokerContractSuite`, `MarketCoverageContract`, `MarketSurface`, test import repair, paper enrolled.
- REF-1/2/4/5: **Partial** — kernel modules in `brokers/common/` (`transport`, `acl`, `margin_provider`, `auth/TokenLifecycle` re-export); Upstox margin unified; Dhan WS reconnect still inline in places.
- REF-6: **Done** — use-case layer (`place_bracket`, `exit_all`, `gtt`, `pnl_exit`, `depth`).
- REF-7/8: **Done** — full surface moved to `dhan/wire.py`, `upstox/wire.py`; factories return wire adapters.
- REF-4b gateway deletion: **Done** — `gateway.py` removed; ~55 imports retargeted to `wire`.
- REF-9 paper: **Done** — paper certifies 32/32; contract + market coverage enrolled.
- REF-10/11: **Partial** — ADR-014/README updated, graphify refreshed; physical `plugins/` file move not done (500+ internal imports); import-linter `broker_facade → wire` updated.
- Live cert: paper **CERTIFIED**; dhan **30/32** (historical 5m/1D empty off-hours); upstox **HTTP 423** (account lockout — env, not code).

## Status log (2026-07-11 — standard connect flow enforcement)

- **Done** — `_create_transport_gateway` private; deprecated `create_gateway` shim; `connect_live` / `connect_analytics` / `try_connect_live` in `interface.ui.services.connect`.
- **Done** — 8 UI validation commands + `auth_live_probe` + `broker_manager` datalake migrated off raw transport.
- **Done** — integration conftest/contract fixtures use `bootstrap_gateway(require_authenticated=True)`.
- **Done** — `scripts/_connect.py`; verify/debug/migration scripts use `bootstrap_or_exit`.
- **Done** — import-linter contract `UI commands use connect shims not raw factory`; ruff banned-api for `create_gateway`; `test_connect_flow_compliance.py`.
- **Done** — removed unused `brokers/dhan/auth/wire_lifecycle.py`; README + ADR-014 connect contract section.
