# Architectural Audit & Refactoring Plan — `src/brokers`

**Scope:** `src/brokers` (packages: `common`, `dhan`, `upstox`, `paper`)
**Date:** 2026-07-10
**Method:** 4 parallel read-only exploration agents mapped each package + cross-cutting grep sweeps.
**Intended target architecture (from `src/brokers/OBJECT_MODEL_PLAN.md`, superseded 2026-07-09):** gateways demoted to *transports*; domain `Instrument`/`Session` + ports in `domain.ports` are the public surface. README confirms `tradex.connect(...)` → `Session`/`Instrument`/ports; brokers are transports behind `DataProvider`/`ExecutionProvider`/`BrokerAdapter`.

> Key framing: the seams that fix these smells **already exist** (`domain` enums, `domain.status_mapper`, `domain.constants.resilience`, `brokers.common.{backoff,idempotency,order_validation,tick_validation}`, `domain.ports.broker_adapter`). The disease is **incomplete adoption** of those seams, plus duplicated facade/surface code. The plan is therefore mostly "route everything through the seam that already exists" + "delete the second copy."

---

## PHASE 1 — Codebase Mapping

### 1.1 Modules & Stated Responsibilities

| Package | Subpackages | Responsibility |
|---|---|---|
| `common` | `api`, `contracts`, `instruments`, `oms` | Thin shared utility layer. NOT a re-export facade (`common/__init__.py` declares `__all__=[]`). |
| `dhan` | `api`, `auth`, `config`, `data`, `domain`, `execution`, `extensions`, `identity`, `instruments`, `portfolio`, `resilience`, `streaming`, `websocket` | Full Dhan transport: HTTP/WS clients, auth/token, order/portfolio/data adapters, extension registry. |
| `upstox` | `adapters`, `auth`, `capabilities`, `config`, `data`, `extensions`, `fundamentals`, `instruments`, `ipo`, `kill_switch`, `mappers`, `market_data`, `market_intelligence`, `mutual_funds`, `news`, `orders`, `payments`, `reconciliation`, `static_ip`, `websocket` | Full Upstox transport: OAuth/token, ~18 feature subpackages. |
| `paper` | (flat) | In-memory sim broker; mirrors gateway surface via `PaperGateway` + `PaperProvider*` adapters to `domain.ports`. |

**`common` real contents (18 modules):** `broker_capabilities.py` (shim → `domain.capabilities.broker_capabilities`), `capabilities_validator.py`, `idempotency.py`, `order_validation.py`, `tick_validation.py`, `backoff.py`, `api/spi.py` (`BrokerSource` enum only), `api/__init__.py` (Margin/Data/Portfolio protocols), `contracts/broker_contract.py` (conformance tests), `contracts/module_test_suite.py`, `instruments/{carrier,keys,service}.py`, `oms/margin_provider.py`.

> NOTE: audit assumptions about `common/{gateway,dtos,models,settings,factory,registry}.py` are **wrong** — those modules do not exist. `common` is much narrower than its name implies. This itself is finding SMELL-13.

### 1.2 Import / Dependency Graph (direction)

- **Outbound (clean):** `domain`, `tradex`, `analytics` import **only** the port (`domain.ports.broker_adapter` / `broker_gateway` / `broker_transport`). Zero deep imports into `brokers.dhan.*` / `brokers.upstox.*` submodules. ✅ Boundary respected outward.
- **Inbound (selective adoption of `common`):** dhan & upstox import `common.{idempotency,order_validation,tick_validation,backoff,broker_capabilities,capabilities_validator,instruments}`, but **not uniformly** (upstox ignores `common.backoff`).
- **Ports live in `domain`, not `common`:** `domain/ports/broker_adapter.py` (`BrokerAdapter = DataProvider + ExecutionProvider`), `domain/ports/protocols.py`, `domain/capabilities/*`. `common/api/spi.py` only holds `BrokerSource`.
- **Intra-package hub:** `dhan/streaming/connection.py` depends on ~20 sibling modules (depth pools, token mgr, conditional triggers, etc.).

### 1.3 Shared Vocabulary — where each lives & where it's duplicated

| Concept | Canonical home | Used by | Duplicated / bypassed by |
|---|---|---|---|
| `OrderType`/`ProductType`/`Side`/`Validity` | `domain/enums` | both brokers ✅ | none major |
| order `status` map | `domain.status_mapper` (`COMMON_STATUS_MAP`, `StatusMapperRegistry`) | both brokers (via `dhan/status_mapper.py`, `upstox/status_mapper.py`) | status normalization **bypassed** in dhan super/forever orders; upstox GTT/cover/slice adapters |
| price wire conversion | `domain.value_objects.price.to_wire_float` | both brokers ✅ | ~260 raw `Decimal(str(...))` sites in both |
| backoff | `common/backoff.exponential_backoff` + `domain.constants.resilience` | **dhan only** | **upstox re-implements** (`v3_auto_reconnect.next_delay`, `auth/http._backoff`) |
| exchange short codes `NSE/NFO/MCX/BSE/CDS` | `domain/constants/exchanges.py` | **neither** — module unused | hardcoded ~50+ sites; dhan keeps its own `Exchange` enum (`dhan/domain.py`) + `segments.py` |
| `ExchangeSegment`/`InstrumentType` | `domain/market_enums.py` | upstox | dhan keeps `DhanInstrumentType` + `segments.py` |
| margin port | `common/api.MarginProvider` | upstox (direct), `common/oms/margin_provider` (bridge) | dhan `MarginAdapter` does **not** implement it |

---

## PHASE 2 — Shotgun Surgery Detection

Format: `[SMELL-N] <Pattern>` · Files · Symbol/Value · Blast Radius · Impact.

**[SMELL-1] A — Scattered exchange-code literals (BOTH brokers)**
Files: dhan `gateway.py` (174,177,180,186,199,212,238,309,324,328,335), `streaming/connection.py` (357,407,411,446,450), `data/market_data.py` (32,60,84,115,124,148), `extended.py`, `domain.py`; upstox `gateway.py` (103,106,109,112,115,119,125,175,178,184), `adapters/market_data_gateway.py`, `adapters/order_gateway.py`, `adapters/streaming_gateway.py`, `data_provider.py`, `instruments/service.py`, `adapters/stream_manager.py`.
Symbol/Value: `"NSE"`, `"NFO"`, `"BSE"`, `"MCX"`, `"CDS"` (50+ sites). Canonical `domain/constants/exchanges.py` exists but is imported **nowhere** in either broker.
Blast Radius: 10+ files per broker per rename.
Impact: HIGH

**[SMELL-2] A — Duplicated capability frozensets (BOTH brokers, verbatim)**
Files: `dhan/config/capabilities.py` (135-136), `upstox/capabilities/snapshot.py` (152-153).
Symbol/Value: `product_types=frozenset({"INTRADAY","MARGIN","CNC",...})` and `order_types=frozenset({"MARKET","LIMIT","STOP_LOSS","STOP_LOSS_MARKET"})` — byte-identical copies; plus `upstox/mappers/_base.py` (42-62) and `upstox/capabilities/snapshot.py` (152-153) are a 3rd copy of the product/order vocabulary.
Blast Radius: 4-5 files.
Impact: MEDIUM

**[SMELL-3] A — `_NSE_SEGMENTS` frozenset duplicated 3×**
Files: `dhan/extensions/depth20.py:29`, `dhan/extensions/depth200.py:27`, `upstox/extensions/depth.py:29`.
Symbol/Value: `frozenset({"NSE","NSE_EQ","NFO","NSE_FNO","IDX_I"})` — identical; also a bare tuple of same in `dhan/streaming/connection.py:411,450`.
Blast Radius: 3-4 files.
Impact: MEDIUM

**[SMELL-4] A — Segment↔exchange maps defined in ≥4 independent spots (upstox)**
Files: `upstox/instrument_adapter.py` (99-123), `upstox/instruments/segment_mapper.py` (59-67), `upstox/mappers/_base.py` (134-141), `upstox/extensions/depth.py:29`. dhan: `dhan/segments.py` (30-65), `dhan/domain.py` (`Exchange` enum).
Symbol/Value: `NSE_EQ→NSE`, `NSE_FO→NFO`, `MCX_FUT→MCX`, …
Blast Radius: 4-5 files.
Impact: MEDIUM

**[SMELL-5] A — Reconnect/refresh/timeout magic numbers**
Files: dhan `websocket/connection.py` (backoff `1.0`/`30.0` 217-218; env `DHAN_MAX_RECONNECT_ATTEMPTS=50`, `DHAN_RECONNECT_COOLDOWN_SECONDS=300`, `DHAN_STALENESS_THRESHOLD_SECONDS=60`; `30s`/`5s` joins); `data/depth_feed_base.py` (452-453); `loader.py:217` (`timeout=30`); upstox `v3_auto_reconnect.py:15-17` (`10.0`/`50`), `auth/config.py:65-66` (`10`/`5` — **mismatch with 50**), `auth/config.py:14-23`, `token_manager.py:37` (`30.0`), `totp_scheduler.py:45-46` (`refresh_hour=8`), `auth/http.py:80` (`15.0`), `login.py:134` (`300.0`).
Symbol/Value: backoff/retry/refresh constants. dhan partly env-overridable; upstox hardcoded; **`ws_reconnect_max_retries` default 5 vs 50** mismatch inside upstox.
Blast Radius: 4-6 files.
Impact: HIGH (silent behavior divergence)

**[SMELL-6] B — Three parallel backoff implementations**
Files: `common/backoff.py:10` (`exponential_backoff`), `dhan/api/reconnecting_service.py` + `dhan/resilience/retry_executor.py` + `dhan/config/config.py:123-132` (`RetryConfig.calculate_backoff`), `upstox/websocket/v3_auto_reconnect.py:39` (`next_delay`) + `upstox/auth/http.py:414` (`_backoff`).
Symbol/Value: exponential backoff. upstox never imports `common.backoff` or `domain.constants.resilience`.
Blast Radius: 3 files (one per impl) + every caller.
Impact: HIGH

**[SMELL-7] B — Two HTTP-base/endpoint sources per broker**
Files: dhan `api/http_client.py:28`, `api/async_http_client.py:64`, `config/settings.py:40`, `config/config.py:21` (all re-bind `Dhan.REST_BASE`); upstox `auth/config.py:142-149` + `auth/urls.py` (URLs duplicated across two files), `config/endpoints.py`.
Symbol/Value: REST base + OAuth URLs.
Blast Radius: 4 files (dhan), 2-3 (upstox).
Impact: MEDIUM

**[SMELL-8] B — Order/status normalization: two wire-parsing paths + bypass sites**
Files: canonical `domain.status_mapper` → `dhan/status_mapper.py:12-22` / `upstox/status_mapper.py:12-27` (register maps); applied via `dhan/websocket/order_stream.py:384` (`OrderStatus.normalize`) vs `upstox/mappers/_base.py:73` (`wire_status_to_domain_status`). Bypassed: dhan `execution/super_orders.py:340,361`, `forever_orders.py:309` (raw `orderStatus` strings into domain `Order`); upstox `orders/gtt_adapter.py`, `cover_order_adapter.py`, `slice_adapter.py` (build `Order` with no/empty status). Root cause: `domain.py` types `order_status` as `str` (dhan `domain.py:198,218,252`).
Blast Radius: 6-8 files.
Impact: HIGH

**[SMELL-9] B — Margin parsing duplicated 3 ways**
Files: `common/oms/margin_provider.py` (`_parse_margin_response`), `dhan/portfolio/margin.py:80` (`MarginResponse`), `upstox/market_data/margin.py` | `upstox/market_data/margin_adapter.py` (`UpstoxMarginAdapter(MarginProvider)`) vs dhan `MarginAdapter` (does NOT implement `MarginProvider`).
Symbol/Value: `totalMargin`/`orderMargin`/`spanMargin`/`exposureMargin` field normalization.
Blast Radius: 3 files.
Impact: MEDIUM

**[SMELL-10] B — Token refresh: parallel trees under `auth/`**
Files: dhan `auth/token_manager.py`, `token_scheduler.py`, `connection_token_manager.py`; upstox `auth/token_manager.py`, `token_expiry.py`, `totp_scheduler.py`, `totp_client.py`, `pkce.py`, `oauth_client.py`. upstox also `auth/holders.py` (5 token-holder classes), `encrypted_token_state_store.py`, `json_token_state_store.py`.
Symbol/Value: token lifecycle. Same folder name, independent implementations; upstox more fragmented.
Blast Radius: 6-10 files.
Impact: MEDIUM

**[SMELL-11] C — Cross-module wiring hub mutates sibling state**
Files: `dhan/streaming/connection.py:11-118` (wires `_orders`, `_super_orders`, `_forever_orders`, `_pnl_exit`, `_exit_all`, `_depth_*`); reaches into ~20 sibling modules directly. upstox `broker.py:157-243` (`_build_raw_clients`/`_build_adapters`/`_build_order_path` build ~30 clients) — a god-object wiring facade.
Symbol/Value: `DhanConnection` / `UpstoxBroker` construct & own half the broker's collaborators.
Blast Radius: every feature file (5-6 per feature).
Impact: HIGH

**[SMELL-12] D — `extended.py` name collision, opposite contents**
Files: `dhan/extended.py` (`DhanExtendedCapabilities` = derivatives expiries/chains/`validate_order`), `upstox/extended.py` (`UpstoxExtendedCapabilities` = IPO/PnL/news/fundamentals).
Symbol/Value: same module name, different surface. Readers importing `brokers.<x>.extended` get non-parity. Also `common_extensions.py` at different depths (`dhan/extensions/common_extensions.py` vs `upstox/common_extensions.py`) with different extension sets; duplicate class names `DhanSuperOrderExtension`/`DhanForeverOrderExtension` appear twice each (in `extensions/*` and `extensions/common_extensions.py`).
Blast Radius: 2-4 files.
Impact: MEDIUM

**[SMELL-13] D — Phantom `common` (stale references to a gutted package)**
Files: 12+ docstring/comment references: `brokers.common.core.domain` (`dhan/gateway.py:316`, `upstox/adapters/streaming_gateway.py:70`), `brokers.common.core.exchange_segments` (`dhan/segments.py:3`), `brokers.common.lifecycle.ManagedService` (`dhan/resolver_refresher.py:17`, `upstox/auth/totp_scheduler.py:6`), `brokers.common.adapters` (`upstox/common_extensions.py:157`, `upstox/factory.py:65`), `brokers.common.tests.certify_broker` (`interface/ui/commands/certify.py:25`), `brokers.common.batch_mixin` (`datalake/gateway.py:215`), `brokers.common.bootstrap` (`infrastructure/gateway/provider_factory.py:10`).
Symbol/Value: docs point at modules that no longer exist. Creates false mental model of where canonical types live.
Blast Radius: 12+ files (documentation only, but misleads refactors).
Impact: MEDIUM

**[SMELL-14] E — Fragmented feature ownership (super/forever orders)**
Files (dhan super order): `execution/super_orders.py`, `extensions/super_order.py`, `extensions/common_extensions.py:30`, `extended.py:92-106`, `streaming/connection.py:55` (5 files, duplicate class name). Same pattern for forever orders (`execution/forever_orders.py`, `extensions/forever_order.py`, `extensions/common_extensions.py:82`, `extended.py:110-124`, `streaming/connection.py:56`). upstox forever (=GTT): `orders/gtt_adapter.py`, `orders/gtt_client.py`, `extended.py:238-252`, `common_extensions.py:120-146` (triple-implemented; stub `success=False` in one).
Symbol/Value: one business feature split across 3-5 files with parallel registry + facade + adapter + client + wiring.
Blast Radius: 5-6 files per feature.
Impact: HIGH

**[SMELL-15] E — Fragmented feature: exit-all / depth / pnl-exit**
Files: dhan exit-all `execution/exit_all.py`+`extended.py:190-192`+`streaming/connection.py:65` (3); pnl-exit `execution/pnl_exit.py`+`extended.py:220-242`+`connection.py:66` (3); depth `data/depth_20.py`+`data/depth_200.py`+`extensions/depth20.py`+`extensions/depth200.py`+`gateway.py`+`connection.py` (~6). upstox exit-all `orders/exit_all_adapter.py`+`kill_switch/*`+`broker.py:218,399` (**latent bug: `self.exit_all` never defined**).
Blast Radius: 3-6 files.
Impact: MEDIUM

**[SMELL-16] F — Mirror gateways / adapter hierarchies (lockstep)**
Files: `DhanBrokerGateway` (`dhan/gateway.py:27`) vs `UpstoxBrokerGateway` (`upstox/gateway.py:57`); `UpstoxBroker` (`upstox/broker.py:78`) is the root object dhan lacks. Parallel `*Adapter` pairs: `dhan/portfolio/portfolio.py:18 PortfolioAdapter` ↔ `upstox/adapters/portfolio_adapter.py:18 PortfolioAdapter`; `dhan/data/market_data.py:16 MarketDataAdapter` ↔ `upstox/adapters/market_data_gateway.py:31 MarketDataGateway`; `dhan/execution/orders.py:64 OrdersAdapter` ↔ `upstox/adapters/order_gateway.py:29 OrderGateway`. upstox has **two** `PortfolioAdapter` classes (`adapters/portfolio_adapter.py` vs `market_data/portfolio_adapter.py`) returning slightly different shapes.
Symbol/Value: same surface hand-maintained in two packages; upstox internally has duplicate adapter names.
Blast Radius: 2+ per method.
Impact: HIGH

**[SMELL-17] G — Inconsistent abstraction level (raw dict vs domain)**
Files: upstox `orders/order_query_adapter.py:21-31` (returns `body.get("data")` raw), `gtt_client.py`/`kill_switch/client.py`/`news/client.py` (raw dict), `data_provider.py:223-234` (accepts dict OR object), `tick_translator.py:65,82` (returns raw dict on failure); `gateway.py:244-256` reaches **private** infra (`_read_circuit_breaker`, `token_manager.refresh_count`, `rate_limiter`); dhan `extended.py:317` raw `self._conn.client.post("/optionchain/expirylist", json={...})` bypassing `OptionsAdapter`; dhan `gateway.future_chain` builds dicts from raw `c` dicts; `execution/super_orders.py`/`forever_orders.py` inject raw broker status strings into `Order` because `order_status: str`.
Symbol/Value: mixed `Order`/`dict`, `Quote`/`dict`, raw `{"data":...}`, private-attribute reaches.
Blast Radius: 6+ files.
Impact: HIGH

**[SMELL-18] G — Reconnect loop duplication (two live WS loops in dhan)**
Files: `dhan/websocket/connection.py:209-351` (full reconnect w/ env guards), `dhan/data/depth_feed_base.py:404-419` (**re-implements** backoff inline despite importing `ReconnectingServiceMixin` which it doesn't use), `dhan/api/reconnecting_service.py` (`ReconnectingServiceMixin`), plus `_emit_reconnect_metric` duplicated verbatim in `connection.py:472-478` & `reconnecting_service.py:186-192`.
Symbol/Value: WebSocket reconnect + backoff + reconnect-state fields (`_stop_event`,`_reconnect_count`,`_last_message_at`).
Blast Radius: 3 files (dhan depth feed diverges from market feed).
Impact: HIGH

**[SMELL-19] H — `paper` duplicates order/position logic; bypasses shared validators**
Files: `paper/paper_orders.py` (`_place_internal` 243-354 re-implements `application.oms` order/position state; synthethic fills bypass `common.order_validation`); `paper/paper_portfolio.py:31` (`get_balance` recomputes margin from positions — no shared helper); paper implements `DataProvider`/`ExecutionProvider` via `PaperDataProvider`/`PaperExecutionProvider` but **not** `MarginProvider` and never calls `common.idempotency`.
Symbol/Value: OMS behavior re-implemented; validators applied inconsistently across 3 brokers.
Blast Radius: 3 files.
Impact: MEDIUM

**[SMELL-20] F — Subpackage sprawl / mirrored top-level ↔ subpackage (dhan)**
Files: `extended.py` ↔ `extensions/*`; `status_mapper.py` ↔ `domain.status_mapper`; `resolver.py`/`instruments/service.py`/`identity/identity.py` (resolver in 3 places); `loader.py` ↔ `instruments/service.py`; `symbol_validator.py` ↔ `execution/order_validator.py`; `streaming/connection.py` vs `websocket/connection.py` (same filename, different role); `data/depth_feed_base.py` (WS impl in `data/`). `config/` has 6 files, 3 re-bind `Dhan.REST_BASE`.
Symbol/Value: same concept at two locations.
Blast Radius: 2-3 files each.
Impact: MEDIUM

**[SMELL-21] H — `UpstoxBroker.capabilities` vs `UpstoxBrokerGateway.capabilities` divergence**
Files: `upstox/broker.py:359` (`_UpstoxCapabilities` dataclass) vs `upstox/gateway.py:213` (`BrokerCapabilities`). Also `gateway.py` reaches into adapter internals (`_stream_registry`, `_stream_lock`, `_resolve_instrument_key`, `_translate_tick_to_quote`).
Symbol/Value: two capability shapes for one broker.
Blast Radius: 2 + all capability consumers.
Impact: MEDIUM

**[SMELL-22] B — Price parsing not universal**
Files: `upstox/mappers/price_parser.py` (`UpstoxPriceParser`, the clean V2-rupees/WS-paise splitter) is **not** called by `tick_translator.py` or `data_provider.py`, which use raw `Decimal(str(val))`. dhan `streaming/connection.py:384-390`, `websocket/_helpers.py` likewise raw.
Symbol/Value: paise-vs-rupee distinction can be lost on WS path.
Blast Radius: 4-5 files.
Impact: MEDIUM

---

## PHASE 3 — Root Cause Classification

1. **Missing shared vocabulary layer (constants/enums not centralized/used)**
   - SMELL-1 (exchange codes), SMELL-2 (capability frozensets), SMELL-3 (`_NSE_SEGMENTS`), SMELL-4 (segment maps), SMELL-5 (timeout numbers). The canonical modules (`domain/constants/exchanges.py`, `domain.constants.resilience/timeouts`) exist but are imported by **neither** broker uniformly.

2. **Missing service / use-case layer (business logic leaking into I/O/UI)**
   - SMELL-8 (status bypassed at I/O), SMELL-11 (wiring god-objects), SMELL-17 (facade reaches raw HTTP/private infra), SMELL-19 (paper re-implements OMS), SMELL-21 (capability computed in facade).

3. **Missing domain model (raw primitives instead of typed entities)**
   - SMELL-8 (domain `Order.order_status: str`), SMELL-17 (raw dict returns), SMELL-22 (price not typed through `price_parser`).

4. **Boundary violations (importing across layer boundaries)**
   - SMELL-17 (private-attribute reaches), SMELL-20/SMELL-11 (intra-package hub reaching deep siblings). Outbound `domain`/`tradex` boundary is clean ✅.

5. **Premature / excessive file splitting (one concept across files, no unifying interface)**
   - SMELL-12 (`extended.py` semantics), SMELL-14/15 (feature fragmentation), SMELL-16 (mirror adapters), SMELL-20 (subpackage sprawl), SMELL-7 (base-URL copies).

6. **Absent / inconsistent coding standards (naming, error, logging)**
   - SMELL-6 (backoff re-implemented), SMELL-9 (margin parse x3), SMELL-10 (token tree), SMELL-13 (phantom `common` docs), SMELL-18 (reconnect re-implemented), SMELL-12 (duplicate class names). No import linter, no `__all__` discipline beyond `common`.

---

## PHASE 4 — Refactoring Plan

Sequencing: foundational constants/types (REF-1..4) → shared resilience (REF-5..6) → domain type/return discipline (REF-7..9) → collapse mirrored surfaces (REF-10..13) → feature consolidation (REF-14..16) → paper parity (REF-17) → docs/guardrails (REF-18..19).

**REF-1 — Centralize exchange & segment vocabulary**
- Root Cause: 1
- Action: Move `NSE/NFO/BSE/MCX/CDS/BFO` + segment wire strings into `domain/constants/exchanges.py` (already exists, currently unused). Add `SEGMENT_TO_EXCHANGE`/`EXCHANGE_TO_SEGMENT` single maps. **Delete** dhan `segments.py` map + `Exchange` enum in `dhan/domain.py`; replace upstox `instrument_adapter.py` (99-123), `instruments/segment_mapper.py`, `mappers/_base.py` segment funcs, `extensions/depth.py` maps to import from `domain`.
- From: `dhan/segments.py`, `dhan/domain.py`, `upstox/instrument_adapter.py`, `upstox/instruments/segment_mapper.py`, `upstox/mappers/_base.py`, `upstox/extensions/depth.py`, `dhan/extensions/depth20.py`, `dhan/extensions/depth200.py`
- To: `domain/constants/exchanges.py`
- Touches: SMELL-1,2,3,4 (≈12 files)
- Test: grep that `NSE` literal no longer appears outside `domain/constants/exchanges.py`; `BrokerContractSuite` still passes; unit test mapping round-trips.
- Sequencing: none.

**REF-2 — Single source for capability/product/order-type vocab**
- Root Cause: 1
- Action: Define `SUPPORTED_PRODUCT_TYPES`/`SUPPORTED_ORDER_TYPES`/`SUPPORTED_VALIDITIES` once in `domain/capabilities` (or `domain/constants`). Both `dhan/config/capabilities.py` and `upstox/capabilities/snapshot.py` import the shared frozenset; delete local copies; add `_NSE_SEGMENTS` to `exchanges.py` and import in both `depth` extensions.
- From: `dhan/config/capabilities.py:135-136`, `upstox/capabilities/snapshot.py:152-153`, `upstox/mappers/_base.py:42-62`, `dhan/extensions/depth20.py:29`, `dhan/extensions/depth200.py:27`, `upstox/extensions/depth.py:29`
- To: `domain/constants/*` (shared)
- Touches: SMELL-2,3,4 (≈6 files)
- Test: assert the two brokers' capability frozensets are identical post-merge; contract tests.
- Sequencing: after REF-1.

**REF-3 — Centralize resilience/timeout constants**
- Root Cause: 1
- Action: Put reconnect/refresh/backoff defaults in `domain/constants/resilience.py` + `timeouts.py` (dhan already uses these; upstox does not). Make `ws_reconnect_max_retries`/`interval` a single constant; fix the **5-vs-50** mismatch (upstox `auth/config.py:65-66` vs `v3_auto_reconnect.py:17`).
- From: `dhan/websocket/connection.py`, `dhan/data/depth_feed_base.py`, `upstox/v3_auto_reconnect.py`, `upstox/auth/config.py`, `upstox/auth/token_manager.py`, `upstox/totp_scheduler.py`, `upstox/auth/http.py`
- To: `domain/constants/resilience.py`, `timeouts.py`
- Touches: SMELL-5,6 (≈7 files)
- Test: unit test reading the constant; assert upstox reconnect default == dhan default.
- Sequencing: none (parallel to REF-1).

**REF-4 — Single endpoint/URL source per broker**
- Root Cause: 5
- Action: One `endpoints.py` constant per broker (`Dhan.REST_BASE`, OAuth URLs). dhan: keep `config/endpoints.Dhan` but stop re-binding in `http_client.py`/`async_http_client.py`/`settings.py`/`config.py` (4→1). upstox: merge `auth/config.py` URL getters + `auth/urls.py` + `config/endpoints.py`.
- From: see SMELL-7
- To: each broker's `config/endpoints.py`
- Touches: SMELL-7 (≈6 files)
- Test: import-only test; assert `REST_BASE` resolves to one value.
- Sequencing: none.

**REF-5 — One backoff implementation**
- Root Cause: 6
- Action: Force both brokers through `common/backoff.exponential_backoff` (or `domain.constants.resilience.ExponentialBackoff`). Delete upstox `v3_auto_reconnect.next_delay` + `auth/http._backoff`; have `UpstoxAutoReconnect` and dhan `ReconnectingServiceMixin` call the shared fn. Retire dhan `RetryConfig.calculate_backoff` if redundant.
- From: `upstox/websocket/v3_auto_reconnect.py:39`, `upstox/auth/http.py:414`, `dhan/config/config.py:123-132`, `dhan/resilience/retry_executor.py`
- To: `common/backoff.py` (or `domain.constants.resilience`)
- Touches: SMELL-6,18 (≈5 files)
- Test: unit test backoff sequence identical across both brokers.
- Sequencing: after REF-3.

**REF-6 — Unify WebSocket reconnect loop (dhan)**
- Root Cause: 6
- Action: Make `dhan/data/depth_feed_base.py` actually use `ReconnectingServiceMixin._backoff_sleep` (it already imports the mixin but ignores it). Extract shared reconnect-state (`_stop_event`,`_reconnect_count`,`_last_message_at`,`_emit_reconnect_metric`) into `common` or `brokers.common.api`. One reconnect primitive for market-feed + depth-feed.
- From: `dhan/websocket/connection.py`, `dhan/data/depth_feed_base.py`, `dhan/api/reconnecting_service.py`
- To: shared mixin in `common`
- Touches: SMELL-18 (≈3 files)
- Test: reconnect integration test; assert identical backoff/metric behavior.
- Sequencing: after REF-5.

**REF-7 — Type `Order.order_status` as `OrderStatus`**
- Root Cause: 3
- Action: Change `domain.py` (dhan) `order_status: str` → `OrderStatus` on `Order`/`SuperOrder`/`ForeverOrder`. Force all writers through `StatusMapperRegistry.normalize_strict`. Bump raw-string writers: `execution/super_orders.py`, `execution/forever_orders.py`, upstox `gtt_adapter.py`, `cover_order_adapter.py`, `slice_adapter.py`.
- From: `dhan/domain.py:198,218,252`, `dhan/execution/super_orders.py:340,361`, `forever_orders.py:309`, `upstox/orders/{gtt,cover,slice}_adapter.py`
- To: `domain/status_mapper` + typed field
- Touches: SMELL-8 (≈6 files)
- Test: type check (mypy/pyright); contract test asserts `Order.order_status` always enum.
- Sequencing: after REF-1 (status map already shared).

**REF-8 — Enforce domain return types (no raw dict)**
- Root Cause: 3,4
- Action: Add to `domain/ports` a rule: gateway/adapter public methods return typed `Order`/`Quote`/`Depth`/`Candle`, never raw `{"data":...}` or `dict`. Wrap raw `order_query_adapter`/`gtt_client`/`tick_translator` outputs via the existing mappers. `tick_translator` must return `Quote`, not raw dict on failure (raise typed error instead). Ban `gateway.py:244-256` private-attribute reaches via review.
- From: `upstox/orders/order_query_adapter.py`, `gtt_client.py`, `kill_switch/client.py`, `news/client.py`, `data_provider.py`, `tick_translator.py`, `upstox/gateway.py:244-256`, `dhan/extended.py:317`
- To: `domain.ports` typed returns + `domain/mappers` (already exist)
- Touches: SMELL-17,22 (≈8 files)
- Test: contract test asserts return types; grep ban on `body.get("data")` in public adapters.
- Sequencing: after REF-7.

**REF-9 — Route price through `price_parser` everywhere**
- Root Cause: 3
- Action: Make `UpstoxPriceParser` (`upstox/mappers/price_parser.py`) the sole price decoder; call it from `tick_translator.py` + `data_provider.py`; dhan route through `domain.value_objects.price.to_wire_float` (already partially).
- From: `upstox/tick_translator.py`, `upstox/data_provider.py`, `dhan/streaming/connection.py`, `dhan/websocket/_helpers.py`
- To: `price_parser` / `to_wire_float`
- Touches: SMELL-22 (≈4 files)
- Test: unit test paise↔rupee round-trip on WS + REST.
- Sequencing: none.

**REF-10 — Collapse `brokers.common.broker_capabilities` shim**
- Root Cause: 5
- Action: Delete `common/broker_capabilities.py`; point `dhan/config/capabilities.py` + `upstox/capabilities/snapshot.py` + `paper/paper_gateway.py` directly at `domain.capabilities.broker_capabilities`.
- From: `common/broker_capabilities.py`, 3 importers
- To: `domain.capabilities.broker_capabilities`
- Touches: SMELL-13 (4 files)
- Test: import test; capability builder unit tests.
- Sequencing: none.

**REF-11 — Reconcile `UpstoxBroker.capabilities` vs `UpstoxBrokerGateway.capabilities`**
- Root Cause: 2
- Action: `UpstoxBrokerGateway.capabilities` should be the single source; have `UpstoxBroker` delegate to it instead of building `_UpstoxCapabilities` (broker.py:359-417). Remove gateway's private-attr reaches (`_stream_registry`, `_resolve_instrument_key`, metrics pokes).
- From: `upstox/broker.py:359`, `upstox/gateway.py:213,244-256`
- To: single capability builder in gateway
- Touches: SMELL-21,17 (≈2 files)
- Test: capability contract test passes for both surfaces identically.
- Sequencing: after REF-10.

**REF-12 — De-duplicate adapter names (upstox)**
- Root Cause: 5
- Action: Merge `adapters/portfolio_adapter.py` `PortfolioAdapter` and `market_data/portfolio_adapter.py` `UpstoxPortfolioAdapter` into one `PortfolioProvider` implementation; remove `MarketDataGateway` wrapping `UpstoxMarketDataAdapter` twice (`gateway.py:64,73`). Rename `mappers/` vs `adapters/` per ADR (see Phase 5).
- From: `upstox/adapters/portfolio_adapter.py`, `upstox/market_data/portfolio_adapter.py`, `upstox/adapters/market_data_gateway.py`, `upstox/gateway.py`
- To: one portfolio adapter + one market-data adapter
- Touches: SMELL-16 (≈4 files)
- Test: provider contract test; no behavior change.
- Sequencing: after REF-8.

**REF-13 — Fix `extended.py` semantics / duplicate class names (dhan)**
- Root Cause: 5,6
- Action: Decide one convention: `extended.py` = broker-specific extras facade; `extensions/*` = plugin surface; `extensions/common_extensions.py` = registry. Rename the **duplicate** `DhanSuperOrderExtension`/`DhanForeverOrderExtension` (the `Provider` subclasses in `common_extensions.py`) to `DhanSuperOrderProvider`/`DhanForeverOrderProvider` to remove the name collision with `extensions/*Extension`. Document that dhan `extended.py` (derivatives) ≠ upstox `extended.py` (IPO/news) — add module docstrings clarifying non-parity, or rename upstox's to `extras.py`.
- From: `dhan/extensions/super_order.py`, `dhan/extensions/common_extensions.py:30`, `dhan/extensions/forever_order.py`, `dhan/extensions/common_extensions.py:82`, `dhan/extended.py`
- To: renamed providers + docstrings
- Touches: SMELL-12,14 (≈5 files)
- Test: import test; registry test.
- Sequencing: after REF-14 (feature consolidation) to avoid churn.

**REF-14 — Consolidate feature chains (super/forever/exit-all/depth)**
- Root Cause: 2,5
- Action: For each feature, define ONE adapter (impl) + register at ONE extension entry + ONE facade method + ONE wiring point. Delete the duplicate provider classes (REF-13). upstox: make `common_extensions.UpstoxForeverOrderExtension` actually call `gtt_adapter` (currently stub `success=False`). Fix latent bug: `upstox/broker.py:399` references undefined `self.exit_all` — wire it or remove.
- From: see SMELL-14,15,21
- To: per-feature single adapter + registry
- Touches: SMELL-14,15,21 (≈12 files)
- Test: feature contract tests (place/cancel super, forever/GTT, exit-all); integration smoke.
- Sequencing: after REF-7, REF-8.

**REF-15 — Merge margin implementations behind `MarginProvider`**
- Root Cause: 2
- Action: Make `dhan/portfolio/margin.py` `MarginAdapter` implement `common/api.MarginProvider` (like upstox `UpstoxMarginAdapter`). Route both through `common/oms/margin_provider.BrokerMarginProvider`; delete duplicated `_parse_margin_response` in dhan.
- From: `dhan/portfolio/margin.py`, `common/oms/margin_provider.py`, `upstox/market_data/margin.py`, `upstox/market_data/margin_adapter.py`
- To: `MarginProvider` port
- Touches: SMELL-9 (≈4 files)
- Test: margin contract test; numeric parity on sample response.
- Sequencing: after REF-8.

**REF-16 — Trim dhan subpackage sprawl**
- Root Cause: 5
- Action: Merge top-level `resolver.py`/`loader.py` into `instruments/service.py`; merge `symbol_validator.py` into `execution/order_validator.py`; move `data/depth_feed_base.py` (WS impl) into `websocket/`. Collapse dhan `config/` 6 files → keep `endpoints.py`+`settings.py`+`config_loader.py` (REF-4). Resolve `streaming/connection.py` vs `websocket/connection.py` naming (rename one, e.g. `streaming/session.py`).
- From: `dhan/resolver.py`, `dhan/loader.py`, `dhan/symbol_validator.py`, `dhan/data/depth_feed_base.py`, `dhan/streaming/connection.py`, `dhan/config/*`
- To: consolidated modules
- Touches: SMELL-20 (≈8 files)
- Test: import + contract tests.
- Sequencing: after REF-1, REF-6.

**REF-17 — Paper parity**
- Root Cause: 2,3
- Action: `PaperGateway` declare `BrokerAdapter` explicitly; add to `common/contracts/broker_contract.py` conformance test (surface already matches). Make `paper_orders` use `_place_via_oms` only (deprecate `_place_internal` duplicated OMS logic). Route paper through `common.idempotency` + `common.order_validation` + `common.tick_validation` for parity. Implement `MarginProvider` for paper (trivial) or document intentional omission.
- From: `paper/paper_gateway.py`, `paper/paper_orders.py`, `paper/paper_portfolio.py`
- To: port-typed + shared validators
- Touches: SMELL-19 (≈3 files)
- Test: `BrokerContractSuite` for PaperGateway; parity test vs dhan/upstox.
- Sequencing: after REF-7, REF-8.

**REF-18 — Fix phantom `common` documentation**
- Root Cause: 6
- Action: Sweep 12+ stale `brokers.common.*` docstring/comment references; repoint to `domain`/`infrastructure`/`application`. Either implement `brokers.common.tests.certify_broker` (referenced at `interface/ui/commands/certify.py:25`) or fix that import.
- From: see SMELL-13 (12 files)
- To: corrected docstrings / real module
- Touches: SMELL-13 (≈12 files)
- Test: grep that no `brokers.common.core.*` / `brokers.common.lifecycle.*` refs remain.
- Sequencing: none (can run early/parallel).

**REF-19 — Module `__all__` + import lint gate**
- Root Cause: 6
- Action: Add explicit `__all__` to every broker public module; add an import-linter rule (see Phase 5 guardrails) forbidding `brokers.<broker>.<deep>` imports from outside `brokers` and forbidding `gateway.*._*` private reaches. Wire into pre-commit/CI.
- From: all broker `__init__.py` + CI config
- To: `__all__` + lint config
- Touches: whole package
- Test: lint passes in CI.
- Sequencing: after REF-8, REF-11 (boundary stable).

---

## PHASE 5 — Structural Recommendations

### 5.1 Proposed Directory Structure (target)

```
src/brokers/
  common/                      # SHARED vocabulary + primitives only
    __init__.py                # __all__=[] (residual, documented)
    backoff.py                 # ONE exponential_backoff()
    idempotency.py             # IdempotencyCache (port + impl)
    order_validation.py        # validate_lot_size / tick_alignment
    tick_validation.py         # is_valid_quote / validate_depth
    api/
      spi.py                   # BrokerSource enum
      __init__.py              # Margin/Data/Portfolio protocols
    contracts/
      broker_contract.py       # BrokerContractSuite (conformance)
      module_test_suite.py
    instruments/
      carrier.py keys.py service.py
    oms/
      margin_provider.py       # BrokerMarginProvider(MarginProvider)
  dhan/  upstox/               # transports; each:
    config/endpoints.py        # ONE REST_BASE + OAuth URLs (REF-4)
    auth/                      # token lifecycle (single manager)
    transport/                 # renamed: old gateway internals behind BrokerTransport
    adapters/                  # ONE adapter per capability (no dup names)
    extensions/                # plugin surface only (Provider subclasses renamed)
  paper/
    paper_gateway.py           # declares BrokerAdapter
    providers/                 # PaperData/Execution/Margin providers
```
Drop: `common/broker_capabilities.py` (shim), dhan top-level `resolver.py`/`loader.py`/`symbol_validator.py`/`extended.py` (fold into adapters/extensions), upstox dual `PortfolioAdapter`, `extended.py` rename to `extras.py`.

### 5.2 Boundary Rules (enforced by import linter)

1. `domain/` and `tradex/` MAY import only `domain.ports.*` / `domain.capabilities.*` — **never** `brokers.dhan.*` / `brokers.upstox.*` submodules. (Already respected; lock it.)
2. `brokers/<x>/gateway.py` (or `transport/`) is the ONLY public surface; everything else is `_private`.
3. Adapters return **typed domain models** (`Order`,`Quote`,`Depth`,`Candle`); never raw `{"data":...}` or `dict`.
4. `Order.order_status` is **always** `OrderStatus` enum — normalized at the boundary via `StatusMapperRegistry`.
5. Resilience/backoff/timeout constants live ONLY in `domain/constants/{resilience,timeouts,exchanges}.py`; brokers import them.
6. `mappers/` = read-model converters (domain←wire); `adapters/` = capability services. One meaning per name. upstox currently conflates them.
7. `common` owns NO broker-specific logic and NO port definitions (ports live in `domain.ports`). `common` = shared primitives only.

### 5.3 Coding Standards to Enforce (checkable)

1. **Exchange/segment codes** come only from `domain/constants/exchanges.py` — grep ban on bare `"NSE"`/`"NFO"`/`"MCX"` literals in `brokers/`.
2. **Prices** use `domain.value_objects.price` / broker `price_parser` exclusively — ban raw `Decimal(str(payload[...]))` in adapters.
3. **Status** normalized via `OrderStatus.normalize`/`StatusMapperRegistry` — no raw broker status strings assigned to `order_status`.
4. **Backoff/reconnect** use `common.backoff` — ban inline `** attempt` / `min(... ** ...)` backoff loops.
5. **Capabilities** built once per broker from shared frozensets — no per-file `frozenset({"MARKET",...})`.
6. **Return types** of public adapter methods are typed domain entities (mypy strict on `brokers/<x>/adapters`, `gateways`).
7. **No duplicate class names** within a package; `Extension` (plugin) vs `Provider` (registry) naming must not collide.
8. **Every public module** declares `__all__`; private collaborators are `_name` and not imported cross-package.

### 5.4 Guardrails to Prevent Recurrence

- **Import linter** (`import-linter` with `forbidden` layers): `domain` ↔ `brokers.<x>.<deep>` forbidden; `brokers.<x>.gateway` ↔ `brokers.<x>._*` internal allowed only. Add to CI.
- **Contract tests**: `BrokerContractSuite` runs against **all three** gateways (dhan, upstox, paper) on every PR — guarantees facade parity and typed returns.
- **mypy/pyright strict** on `brokers/` return types + `OrderStatus` field — catches SMELL-8/17 regressions.
- **ADR template** for any new broker feature: must declare (a) which adapter owns it, (b) which `domain` port it satisfies, (c) where its constants live. Reject PRs that add a new `frozenset`/backoff loop/raw-dict return.
- **Pre-commit grep hook** banning bare exchange literals and `body.get("data")` in `brokers/<x>/adapters`.
- **Module-level `__all__`** + `ruff` `unused`/`redefined` checks to catch duplicate class names (SMELL-12) and dead shims (SMELL-10/13).

---

## Validation Summary

- **Unit:** constant maps, backoff sequence, price paise↔rupee, status normalization.
- **Contract:** `BrokerContractSuite` over dhan + upstox + paper (return types, capability parity, `OrderStatus` always enum).
- **Type:** mypy strict on `brokers/` + `domain`.
- **Lint:** import-linter layers + grep hooks in CI.
- **Integration smoke:** place/cancel super order, GTT/forever, exit-all, depth-20/200, reconnect drop simulation for both brokers.

## Open Questions / Domain-Knowledge Flags

- **NSE margin rules:** `common/oms/margin_provider._parse_margin_response` variants (`spanMargin`/`exposureMargin`) — confirm which fields are authoritative per exchange before merging dhan margin (flagged, not guessed).
- **Upstox `ws_reconnect_max_retries` 5 vs 50:** needs product owner decision on intended default (REF-3).
- **`extended.py` non-parity** (dhan derivatives vs upstox IPO/news) — confirm rename to `extras.py` vs docstring-only fix is acceptable to callers.
- **Paper `MarginProvider`**: confirm whether sim margin is in-scope or intentionally omitted (REF-17).
