# Shotgun-Surgery & Coupling Audit — Trade_XV2

> Code-derived structural audit (graphify-first) dated 2026-07-14.
> Companion to [`PRIORITIZED-AUDIT.md`](PRIORITIZED-AUDIT.md) (correctness/safety, F1–F9)
> and [`CURRENT-STATE.md`](CURRENT-STATE.md). This audit is the **structural/coupling**
> lens the prior one deliberately did not cover: shotgun surgery, scattered constants,
> duplicated logic, cross-module state mutation, fragmented feature ownership, parallel
> hierarchies, inconsistent abstraction levels, and Demeter violations.
>
> Scope note: the working tree was **uncommitted** at audit time (large diff across
> `brokers/`, `datalake/`, `application/`, `infrastructure/`, `interface/`). Findings below
> were verified against the live (uncommitted) source, not the committed snapshot the
> prior docs describe. Some prior findings (F1, F7 partial, F8, F9) are now **partially
> resolved** — noted inline.

---

## Phase 1 — Codebase Mapping

### 1.1 Modules, packages, top-level directories & stated responsibilities

| Directory / module | Stated responsibility (per `architecture.md` §2) | Actual LOC (approx) |
|---|---|---|
| `src/domain/` | Typed model + ports/events. Imports nothing inward. | ~22.6k |
| `src/application/` | Use-cases: OMS, execution, risk, trading orchestrator, portfolio. | ~16.9k |
| `src/infrastructure/` | Adapters: EventBus, gateway factory, resilience, idempotency, observability, auth. | ~16.9k |
| `src/brokers/` | Dhan / Upstox / Paper wire adapters + auth + resilience. | ~42.4k |
| `src/plugins/` | Exchange plugins (`nse/`), the `tradex.exchanges` entry-point group. | small |
| `src/analytics/` | Backtest / replay / paper engines, strategy+feature pipeline, indicators. | ~18.0k |
| `src/interface/` | FastAPI routers + CLI/UI services (composition-ish leaf). | ~21.8k |
| `src/runtime/` | **Single** composition root — the ONLY layer permitted concrete broker imports. | ~2.0k |
| `src/tradex/` | Public SDK session entry (`open_session`) — a **second** composition root. | ~1.1k |
| `src/datalake/` | Historical ingestion/quality/storage/analytics (DuckDB). | ~9.3k |
| `src/config/` | Single `AppConfig` Pydantic schema. | small |
| `web/` | React/TS SPA (Tier 3-I Web Trading UI). | — |
| `tests/` | Mirrors `src/`; architecture tests under `tests/architecture/`. | — |

### 1.2 Import / dependency graph (edge direction = "imports")

```
interface/ (api + ui)        ──▶ application/ ──▶ domain/
   └─ (api no longer imports ui — F9 fixed)        ▲
runtime/ (root)            ──▶ infrastructure/ ─────┘
   └─ imports concrete brokers (ONLY layer allowed)
brokers/                   ──▶ domain/ (ports), infrastructure/ (resilience shared)
analytics/                 ──▶ application/, domain/, infrastructure/ (shared resilience)
datalake/                  ──▶ domain/ (symbols), plugins/ (exchange)
tradex/ (2nd root)         ──▶ runtime/, application/   (duplicates Root A wiring)
```

Edges **violating** the contract (confirmed against current source):
- `src/application/services/historical_data.py` — a **docstring-only stub** (`__all__ = []`) that *recommends* `from infrastructure.historical_data import ...`. The import-linter shows green only because there is no real import — but the file is a latent reconnection trap (see SMELL-7).
- (Resolved) `application/oms/idempotency_guard.py` no longer imports `infrastructure` directly — it depends on the `IdempotencyService` port. **F1 is substantially fixed.**
- (Resolved) `interface/api/*` no longer imports `interface/ui/*`. **F9 is fixed** in current source.

### 1.3 Shared constants, types, enums, config — where each appears

| Shared symbol | Canonical home | Duplicated / divergent copies | Smell |
|---|---|---|---|
| `BrokerId` enum | `src/domain/enums.py:81` | (prior audit claimed a 2nd in `domain/ports/broker_id.py` — **resolved**; `broker_id.py` now re-exports the canonical member) | none live |
| `normalize_symbol` | `src/domain/symbols.py:19` | `src/datalake/core/symbols.py:25` (now delegates to domain — **fixed**) | none live, BUT see SMELL-1 (key format divergence) |
| Backoff constants | `src/domain/constants/resilience.py` (`RETRY_BASE_DELAY_MS`, `MAX_RETRY_DELAY_MS`, `MAX_RETRY_ATTEMPTS`, `BACKOFF_MULTIPLIER`) | `src/infrastructure/resilience/backoff.py`, `src/brokers/common/backoff.py`, inline in `brokers/dhan/api/reconnecting_service.py` | **SMELL-3 / 4** |
| Slippage application | `src/domain/trading_costs.py:179` `apply_slippage` (SSOT) | inline `price*(1±slippage/100)` in `analytics/replay/signal_processor.py:103-104`, `analytics/replay/position_closer.py:92`, `analytics/paper/position_closer.py:118` | **SMELL-2** |
| `_as_money` / `_as_quantity` | (none — triplicated) | `src/domain/entities/order.py:27,35`, `trade.py:13,17`, `position.py:13,21` | **SMELL-5** |
| `risk_free_rate` | (none) | `analytics/options/_greeks.py:57,99` = 0.06; `analytics/facade.py:182` = 0.065; `analytics/backtest/engine.py` `config.risk_free_rate` | **SMELL-3** |
| ATR | `src/domain/indicators/atr.py` (SMA smoothing) | `analytics/pipeline/features.py:38` `ATR` (same SMA); `domain/indicators/halftrend.py:186` (Wilder's) — two ATR *semantics* | **SMELL-5** (domain knowledge flag) |
| Position key | `domain.symbols.make_position_key` (keeps `-EQ`) | `datalake.core.symbols.instrument_id_from_symbol` (strips `-EQ`) | **SMELL-1** |
| Reconciliation interval | `domain/constants/__init__.py:108` `RECONCILIATION_INTERVAL_SECONDS=300` | respected at `application/oms/factory.py` | OK |
| HTTP timeout | `domain/constants/__init__.py:89` `DEFAULT_HTTP_TIMEOUT_SECONDS` | `brokers/dhan/config/settings.py:192` `HTTP_TIMEOUT` default 15.0 (parallel source) | **SMELL-3** |

---

## Phase 2 — Shotgun Surgery Detection

> Ranked by blast radius (highest first). Each entry: type, files, symbol/value, blast radius, impact.

### [SMELL-1] Fragmented feature ownership — symbol/key normalization split-brain (silent key mismatch)
- **Files:** `src/domain/symbols.py`, `src/datalake/core/symbols.py`, `src/datalake/ingestion/normalize.py`, `src/brokers/dhan/instruments/service.py:168`, `src/brokers/upstox/instruments/service.py:189`, `src/plugins/exchanges/nse/adapter.py:41`, `src/infrastructure/instruments.py:28`, `src/domain/instrument_resolver.py:67,211`, `src/interface/ui/commands/market.py:26,137,273`, plus ~10 more inline `strip().upper()` sites.
- **Symbol/Value:** The *canonical* `normalize_symbol` now agrees (datalake delegates to domain). **But the KEY FORMATS diverge**: `make_position_key(sym, exch)` = `normalize_symbol(sym):EXCH` (keeps `RELIANCE-EQ`), while `instrument_id_from_symbol(sym, exch)` = `EXCH:normalize_symbol_for_storage(sym)` (strips `RELIANCE-EQ` → `RELIANCE`). Same instrument → two different keys depending on layer.
- **Blast Radius:** Any flow that bridges OMS positions (`make_position_key`, used in `domain/portfolio_projection.py`, `application/oms/position_manager.py`, `brokers/dhan/data/subscription_engine.py`) with datalake storage (`instrument_id_from_symbol`) — a change to suffix handling must be made in 2+ places with no compiler check.
- **Impact:** HIGH — silent position/storage key disagreement for `*-EQ`/`*-BE` instruments; reconciliation or storage lookups can miss.

### [SMELL-2] Duplicated logic — slippage applied in ≥4 places, bypassing SSOT
- **Files:** `src/domain/trading_costs.py:179` (SSOT `apply_slippage`), `src/analytics/replay/signal_processor.py:103-104,146-147`, `src/analytics/replay/position_closer.py:92`, `src/analytics/paper/position_closer.py:118`, `src/analytics/paper/signal_processor.py:132,176`, `src/application/execution/oms_backtest_adapter.py:151` (correct path).
- **Symbol/Value:** Inline `price * (1 ± slippage_pct/100)` duplicated instead of calling `domain.trading_costs.apply_slippage`. Replay's `fill_recorder.py:83` *does* delegate to SSOT, but `replay/position_closer.py:92` and `replay/signal_processor.py:103` compute it inline — **two slippage code paths inside replay alone**. Paper closer never uses SSOT.
- **Blast Radius:** A change to slippage semantics (e.g., tick-rounding, fee-inclusive) must be edited in 4+ files; missing one silently breaks **zero-parity** between replay and paper.
- **Impact:** HIGH — directly defeats the zero-parity invariant (prior F2a); float math diverges from `Decimal`-based SSOT.

### [SMELL-3] Scattered constants / magic values — resilience & risk params duplicated
- **Files:** `src/domain/constants/resilience.py`, `src/infrastructure/resilience/backoff.py`, `src/brokers/common/backoff.py`, `src/brokers/dhan/api/reconnecting_service.py:18` (inline `1.0 → 30.0 s`), `src/analytics/options/_greeks.py:57,99` (`0.06`), `src/analytics/facade.py:182` (`0.065`), `src/brokers/dhan/config/settings.py:192` (`HTTP_TIMEOUT=15.0` parallel to `DEFAULT_HTTP_TIMEOUT_SECONDS`).
- **Symbol/Value:** Exponential-backoff base/cap/multiplier, risk-free rate, HTTP timeout all defined in multiple homes with differing literals (e.g. `0.06` vs `0.065` risk-free rate; `brokers/common/backoff.py` base `500ms`/cap `5000ms` vs `domain/constants` `RETRY_BASE_DELAY_MS`/`MAX_RETRY_DELAY_MS` vs Dhan inline `1.0→30.0s`).
- **Blast Radius:** A tuning change (e.g. "backoff cap must be 30s everywhere") touches 3–4 files with no shared reference; a literal edit in one location without the others silently changes behavior only on one broker path.
- **Impact:** MEDIUM — behavior desync across brokers; one constant source of truth is bypassed.

### [SMELL-4] Parallel inheritance / mirrored hierarchies — reconnect & retry machinery
- **Files:** `src/brokers/common/transport.py` (`ReconnectingTransport`, shared), `src/brokers/upstox/websocket/v3_auto_reconnect.py` (wraps `ReconnectingTransport` — good), `src/brokers/dhan/api/reconnecting_service.py` (its **own** backoff mixin, `1.0→30.0s`), `src/brokers/dhan/resilience/retry_policies.py` + `retry_executor.py` (re-export of `infrastructure.resilience.retry_executor`), `src/infrastructure/resilience/retry_executor.py`, `src/brokers/common/backoff.py`.
- **Symbol/Value:** Two WS-reconnect strategies (Upstox uses shared `ReconnectingTransport`; Dhan has a bespoke `reconnecting_service.py` mixin with its own backoff arithmetic). Three backoff implementations (`infrastructure/resilience/backoff.py`, `brokers/common/backoff.py`, Dhan inline).
- **Blast Radius:** A behavioral change to "reconnect backoff" must be made in Dhan's mixin AND the shared `transport.py`/`infrastructure` backoff — they do not stay in lockstep (Upstox heals, Dhan may not, or vice-versa).
- **Impact:** MEDIUM — LSP-ish divergence; Dhan vs Upstox reconnect parity (prior P2 note) is not enforced by a shared seam.

### [SMELL-5] Duplicated logic — `_as_money`/`_as_quantity` triplicated; dual ATR semantics
- **Files:** `src/domain/entities/order.py:27,35`, `src/domain/entities/trade.py:13,17`, `src/domain/entities/position.py:13,21`; `src/domain/indicators/atr.py`, `src/domain/indicators/halftrend.py:186`, `src/analytics/pipeline/features.py:38`.
- **Symbol/Value:** Identical `_as_money(value)` / `_as_quantity(value)` coercion helpers copied verbatim across 3 entity modules. ATR: `domain/indicators/atr.py` uses SMA smoothing; `domain/indicators/halftrend.py:186` uses Wilder's; `analytics/pipeline/features.py:38` docs warn "For Wilder's ATR use HalfTrend". Strategies see different ATR depending on which module they import.
- **Blast Radius:** A change to money/quantity coercion touches 3 files; a new indicator importing the "wrong" ATR gets different volatility → different signals.
- **Impact:** MEDIUM — drift in numeric semantics; not a crash but a correctness/parity hazard.

### [SMELL-6] Fragmented feature ownership — multiple OMS / context / dispatcher constructors
- **Files:** `src/domain/runtime_hooks.py:77` (`create_trading_context` — registration indirection), `src/application/oms/factory.py:29` (`create_trading_context` — canonical builder), `src/application/oms/session_bridge.py:225` (`build_oms_service`), `src/runtime/commands/__init__.py:27` (`build_order_dispatcher`), `src/runtime/factory.py:23` + `src/tradex/session.py` (`open_session` — 2nd root wiring).
- **Symbol/Value:** ≥4 distinct construction entry points for the OMS/TradingContext spine, plus a registration-indirection shim in `domain/` that *re-advises* calling `register_trading_context_factory()` at startup. `tradex.open_session` (Root B) wires OMS differently from `runtime.factory.build` (Root A).
- **Blast Radius:** Adding one field to `TradingContext` (e.g. a new risk hook) requires edits in `factory.py`, `session_bridge.build_oms_service`, the `runtime_hooks` registration, and `tradex/session.py` — 4+ files, with the domain shim easily forgotten.
- **Impact:** HIGH — the prior F7 "one composition root / OMS ctor" is **not** fully resolved; the indirection shim in `domain/` is itself a coupling smell (domain importing a wiring concern).

### [SMELL-7] Missing/bypassed abstraction — `application/services/historical_data.py` latent violation trap
- **Files:** `src/application/services/historical_data.py` (entire file), referenced by `src/interface/ui/commands/*` historical flows.
- **Symbol/Value:** The file is a **docstring-only stub** with `__all__: list[str] = []` whose docstring says *"Prefer `from infrastructure.historical_data import HistoricalDataService`"*. It exists purely to "document" where infra lives. It imports nothing, so import-linter is green today — but it is a signpost inviting the exact `application → infrastructure` violation the lint is meant to prevent.
- **Blast Radius:** Any future dev following the docstring reintroduces F1; the stub itself is dead code that must be deleted.
- **Impact:** LOW (now) / MEDIUM (recurrence risk) — dead code + misleading guidance.

### [SMELL-8] Inconsistent abstraction levels — raw `float`/`Decimal` price math in analytics vs typed `Money`
- **Files:** `src/analytics/replay/engine.py`, `src/analytics/replay/signal_processor.py`, `src/analytics/paper/engine.py`, `src/analytics/paper/signal_processor.py`, `src/analytics/backtest/fast_backtest.py:153,171` (`float(_apply_slippage(Decimal(str(price)),...))`), `src/domain/primitives/value_objects.py` (`Money`/`Quantity`).
- **Symbol/Value:** Live/OMS path uses `Money`/`Quantity` VOs; analytics engines pass raw `float`/`Decimal` through price math and only coerce at the boundary. `fast_backtest.py` converts `price→str→Decimal→float` round-trip per fill.
- **Blast Radius:** A change to price precision/scaling must be hunted across every analytics engine; the typed `Money` contract is bypassed on the simulation path.
- **Impact:** MEDIUM — precision/rounding parity gaps between live and sim.

### [SMELL-9] Cross-module state mutation — process globals in `runtime/` + `infrastructure/`
- **Files:** `src/runtime/session_infra.py:59` (`_shared_quota.register_profile`), `src/runtime/broker_infrastructure.py:113` (`quota.register_profile`), `src/brokers/common/transport.py` (global correlation counter), plus prior P3 `G1` process globals (`set_live_actionable_gate`, `require_execution_ledger`, shared quota).
- **Symbol/Value:** Module-level mutable singletons mutated by multiple services; last-writer-wins when ≥2 brokers/services initialize.
- **Blast Radius:** A new broker/profile init path that forgets to register quota silently shares/overwrites global state.
- **Impact:** MEDIUM — runtime desync under multi-broker; no ownership boundary.

### [SMELL-10] Implicit coupling via naming — `normalize_universe_name` & ad-hoc query normalizers
- **Files:** `src/datalake/core/symbols.py:84` `normalize_universe_name` (hand-rolled `upper().replace("_","").replace("-","").replace(" ","")`), `src/brokers/*/instruments/service.py:168,189` (`query.upper().strip()`), `src/domain/status_mapper.py:59` (`broker_status.upper().strip().replace(" ","_")`).
- **Symbol/Value:** At least 5 ad-hoc normalization variants for different string kinds (symbol, exchange, universe, query, broker-status), each re-implemented locally rather than as one parameterized normalizer.
- **Blast Radius:** A new string-kind normalization is likely copy-pasted again; no shared vocabulary for "normalize X".
- **Impact:** LOW–MEDIUM — local duplication; mild inconsistency risk.

---

## Phase 3 — Root Cause Classification

| # | Root cause | SMELLs |
|---|---|---|
| 1 | **Missing shared vocabulary layer** (constants/types/enums/normalizers not centralized) | SMELL-1 (key format), SMELL-3 (constants), SMELL-10 (normalizers), SMELL-5 (`_as_money`/`_as_quantity`) |
| 2 | **Missing service / use-case layer** (business logic leaking into I/O or UI) | SMELL-7 (app stub inviting infra import), SMELL-9 (globals in runtime) |
| 3 | **Missing domain model** (raw primitives instead of typed entities on sim path) | SMELL-8 (float/Decimal vs Money), SMELL-5 (ATR semantics) |
| 4 | **Boundary violations** (modules importing across layers) | SMELL-7 (latent), SMELL-6 (`domain/runtime_hooks` wiring shim = domain↛application leak) |
| 5 | **Premature file splitting** (one concept split without unifying interface) | SMELL-2 (slippage), SMELL-4 (reconnect), SMELL-6 (OMS ctors) |
| 6 | **Absent/inconsistent coding standards** (naming/normalization/abstraction differ per file) | SMELL-3, SMELL-5, SMELL-8, SMELL-10 |

---

## Phase 4 — Refactoring Plan (dependency-ordered)

> Foundational extractions first (constants, types, normalizers, domain helpers), then higher-level
> restructuring. Each REF traces to Phase-2 SMELLs. Test strategy uses integration tests against real
> components per project rules (no mocks).

### REF-1 — Single symbol/key normalization vocabulary
- **Root cause:** 1, 5
- **Action:** Introduce `domain/symbols.py` helpers `make_position_key` AND `make_instrument_id(sym, exch)` that **both** use one canonical suffix policy. Decide suffix policy explicitly (keep vs strip) and apply it in ONE place. `datalake.core.symbols.instrument_id_from_symbol` delegates to domain; remove `normalize_symbol_for_storage` divergence or rename to `make_storage_key` with documented suffix semantics.
- **From:** `src/datalake/core/symbols.py`, `src/domain/symbols.py`
- **To:** `src/domain/symbols.py` (single owner); datalake re-exports.
- **Touches:** `domain/symbols.py`, `datalake/core/symbols.py`, `datalake/ingestion/normalize.py`, `datalake/core/option_format.py`, every `make_position_key`/`instrument_id_from_symbol` caller (position_manager, portfolio_projection, subscription_engine, datalake storage).
- **Test Strategy:** Integration test asserting `make_position_key("RELIANCE-EQ","NSE")` and `make_instrument_id("RELIANCE-EQ","NSE")` agree (or explicitly document the boundary). Parity test bridging OMS position key ↔ datalake storage key.
- **Sequencing:** First. No dependency.
- **Traces to:** SMELL-1.

### REF-2 — Slippage through one function only
- **Root cause:** 1, 5
- **Action:** Force all slippage through `domain.trading_costs.apply_slippage`. Delete inline `price*(1±slippage/100)` in `replay/signal_processor.py`, `replay/position_closer.py`, `paper/position_closer.py`. Add a `ponytail:` note if float rounding is intentional.
- **From:** `src/analytics/replay/*`, `src/analytics/paper/*`
- **To:** `src/domain/trading_costs.py` (SSOT) — callers invoke it.
- **Touches:** `replay/signal_processor.py`, `replay/position_closer.py`, `paper/position_closer.py`, `paper/signal_processor.py`, `domain/trading_costs.py`.
- **Test Strategy:** Integration test: same OHLCV + config → replay fill price == paper fill price (zero-parity). This is the F2a guard.
- **Sequencing:** After REF-1 (needs the normalized symbol keys if slippage keys off symbol).
- **Traces to:** SMELL-2.

### REF-3 — Centralize resilience/risk constants
- **Root cause:** 1, 6
- **Action:** Make `domain/constants/resilience.py` the only home for `RETRY_BASE_DELAY_MS`, `MAX_RETRY_DELAY_MS`, `MAX_RETRY_ATTEMPTS`, `BACKOFF_MULTIPLIER`, plus add `RISK_FREE_RATE` and `DEFAULT_HTTP_TIMEOUT_SECONDS` (already exists — reuse). Delete `brokers/common/backoff.py` (redirect to `domain/constants`) and the inline `1.0→30.0s` in Dhan `reconnecting_service.py`.
- **From:** `src/brokers/common/backoff.py`, `src/brokers/dhan/api/reconnecting_service.py`, `src/analytics/options/_greeks.py`, `src/analytics/facade.py`
- **To:** `src/domain/constants/resilience.py` (+ `market.py` for risk-free rate).
- **Touches:** backoff.py (delete), reconnecting_service.py, _greeks.py, facade.py, any caller of `brokers.common.backoff`.
- **Test Strategy:** Unit test asserting Dhan reconnect cap == Upstox reconnect cap == constant; risk-free-rate single value used everywhere.
- **Sequencing:** Independent; do early (cheap, high leverage).
- **Traces to:** SMELL-3.

### REF-4 — Unify reconnect/retry behind one seam
- **Root cause:** 4, 5
- **Action:** Dhan WS reconnect must use the same `brokers.common.transport.ReconnectingTransport` policy object Upstox uses (REF-3 constants). Delete Dhan's bespoke backoff mixin arithmetic; keep only the thread lifecycle (which genuinely differs). Collapse `brokers/dhan/resilience/retry_executor.py` re-export chain if unused.
- **From:** `src/brokers/dhan/api/reconnecting_service.py`, `src/brokers/dhan/resilience/*`
- **To:** `src/brokers/common/transport.py` (`ReconnectingTransport` + `ResiliencePolicy`).
- **Touches:** reconnecting_service.py, transport.py, dhan websocket feeds, retry_executor.py (delete if dead).
- **Test Strategy:** Integration: kill WS connection on both brokers → both reconnect with identical backoff policy (observability assertion, real components).
- **Sequencing:** After REF-3.
- **Traces to:** SMELL-4.

### REF-5 — One money/quantity coercion helper; one ATR
- **Root cause:** 1, 3
- **Action:** Move `_as_money`/`_as_quantity` to `domain/primitives/value_objects.py` (or a `domain/entities/_coerce.py`); import in order/trade/position. For ATR: pick ONE smoothing (SMA vs Wilder) as canonical `domain/indicators/atr.py`; have `halftrend` import it rather than re-implement. **Flag (domain knowledge):** which ATR smoothing NSE strategy math expects must be confirmed with a quant before collapsing — do not guess.
- **From:** `src/domain/entities/{order,trade,position}.py`, `src/domain/indicators/{atr,halftrend}.py`, `src/analytics/pipeline/features.py`
- **To:** `src/domain/primitives/value_objects.py` + `src/domain/indicators/atr.py`.
- **Touches:** 3 entity files, 2 indicator files, features.py.
- **Test Strategy:** Unit test coercion equivalence; integration test strategy output unchanged after ATR consolidation (only if quant confirms semantics).
- **Sequencing:** Independent; low risk.
- **Traces to:** SMELL-5.

### REF-6 — Single OMS/TradingContext construction entry point
- **Root cause:** 4, 5
- **Action:** Delete the `domain/runtime_hooks.create_trading_context` registration indirection (domain must not own a wiring concern). Make `application/oms/factory.create_trading_context` THE builder; `build_oms_service` and `build_order_dispatcher` wrap it; `tradex.open_session` delegates to `runtime.factory.build` (Root A) — no second OMS wiring.
- **From:** `src/domain/runtime_hooks.py`, `src/application/oms/factory.py`, `src/application/oms/session_bridge.py`, `src/runtime/commands/__init__.py`, `src/tradex/session.py`
- **To:** `src/application/oms/factory.py` (single builder) + `src/runtime/` (composition root only).
- **Touches:** runtime_hooks.py (remove `create_trading_context`), factory.py, session_bridge.py, runtime/commands, tradex/session.py.
- **Test Strategy:** Integration test: build OMS via the single factory from both CLI and SDK entry points; assert identical wiring (same RiskManager/Idempotency ports injected).
- **Sequencing:** After REF-2/3 (no hard dep, but do after foundational extractions to avoid moving broken builders).
- **Traces to:** SMELL-6, SMELL-7 (domain shim).

### REF-7 — Delete `application/services/historical_data.py` stub
- **Root cause:** 2, 4
- **Action:** Delete the docstring-only stub. Historical flows should call the runtime facade (`runtime.historical_data`) or the port, never import `infrastructure` directly. Add an import-linter rule forbidding `application → infrastructure`.
- **From:** `src/application/services/historical_data.py`
- **To:** (deleted); callers use `runtime.historical_data` facade / port.
- **Touches:** historical_data.py (delete), UI command callers.
- **Test Strategy:** import-linter rule `application` may not import `infrastructure` (CI-blocking). Architecture test.
- **Sequencing:** Anytime; cheap.
- **Traces to:** SMELL-7.

### REF-8 — Typed prices on the simulation path
- **Root cause:** 3
- **Action:** Route analytics fill prices through `Money`/`Quantity` (or a single `Price` type) instead of raw `float`/`Decimal` round-trips (`fast_backtest.py:153,171`). Keep precision at the boundary.
- **From:** `src/analytics/{replay,paper,backtest}/*engine*.py`, `fast_backtest.py`
- **To:** `src/domain/primitives/value_objects.py` (`Money`/`Quantity`).
- **Touches:** replay engine, paper engine, backtest engine, fast_backtest, oms_fill_price, oms_backtest_adapter.
- **Test Strategy:** Integration test: replay vs live fill price precision byte-for-byte on a fixed fixture (zero-parity precision check).
- **Sequencing:** After REF-2 (slippage) — do precision work once slippage is centralized.
- **Traces to:** SMELL-8.

### REF-9 — Own process globals explicitly
- **Root cause:** 2, 4
- **Action:** Move `_shared_quota` / correlation counter / `set_live_actionable_gate` into a single `runtime/process_state.py` module injected at composition root; ban module-level mutable singletons elsewhere. Quota registration only via the composition root.
- **From:** `src/runtime/session_infra.py`, `src/runtime/broker_infrastructure.py`, `src/brokers/common/transport.py`, `src/runtime/*` (globals)
- **To:** `src/runtime/process_state.py` (single owner).
- **Touches:** session_infra.py, broker_infrastructure.py, transport.py, any global mutator.
- **Test Strategy:** Integration test: init two broker profiles → quota profiles both present, no last-writer clobber.
- **Sequencing:** After REF-6 (single composition root owns init order).
- **Traces to:** SMELL-9.

### REF-10 — One parameterized string normalizer
- **Root cause:** 1, 6
- **Action:** Add `domain/normalize.py` with `normalize_text(value, *, case="upper", strip=True, drop=None)` and route universe/query/broker-status normalizers through it. Delete `normalize_universe_name` hand-rolling and the inline `upper().strip()` in instrument services/status_mapper.
- **From:** `src/datalake/core/symbols.py:84`, `src/brokers/*/instruments/service.py:168,189`, `src/domain/status_mapper.py:59`, `src/domain/instrument_resolver.py:67,211`
- **To:** `src/domain/normalize.py` (single utility).
- **Touches:** ~6 files.
- **Test Strategy:** Unit test each string-kind normalization equals the old behavior exactly (character-level).
- **Sequencing:** Independent; cheap. Pairs with REF-1.
- **Traces to:** SMELL-10.

---

## Phase 5 — Structural Recommendations

### 5.1 Proposed directory structure (target)

```
src/
  domain/                  # Pure: VOs, entities, ports, ONE normalizer vocab, ONE constants home
    primitives/            #   value_objects.py (Money/Quantity) + coerce helpers (REF-5)
    symbols.py             #   normalize_symbol + make_position_key + make_instrument_id (REF-1)
    normalize.py           #   single parameterized string normalizer (REF-10)
    constants/             #   resilience.py, market.py — ONLY constant homes (REF-3)
    indicators/            #   atr.py canonical; halftrend imports it (REF-5)
  application/             # Use-cases only; NO infra imports (REF-7)
    oms/factory.py         #   SINGLE create_trading_context builder (REF-6)
  infrastructure/          # Adapters implementing domain ports
  brokers/
    common/                #   transport.py = ONLY reconnect/retry seam (REF-4)
  analytics/               # ONE slippage site (REF-2), typed prices (REF-8)
  runtime/                 # Composition root ONLY
    process_state.py       #   single owner of process globals (REF-9)
  interface/  config/  tradex/  datalake/  plugins/
web/
tests/  (mirror src/; architecture tests under tests/architecture/)
```

### 5.2 Boundary rules (import direction — enforce via import-linter)

1. `domain` → **nothing inward** (stdlib + self only). Violation: `domain/runtime_hooks` wiring shim (REF-6).
2. `application` → `domain` ports only. **Never** `infrastructure` (REF-7). Make the prior relaxed lint rule CI-blocking.
3. `brokers` → `domain` + `brokers/common` only. Dhan reconnect MUST use `brokers/common/transport` (REF-4).
4. `analytics` → `domain` (slippage, Money, symbols) + `application` ports. No inline price math (REF-2, REF-8).
5. `runtime`/`tradex` → only composition roots; `tradex.open_session` delegates to `runtime.factory` (REF-6).
6. `interface` → `application` + `runtime`; **never** `brokers` or `interface.ui` (F9 already fixed — keep it).
7. `datalake` → `domain` symbols; storage keys must derive from `domain.symbols` (REF-1).

### 5.3 Coding standards to enforce (checkable)

1. **One normalizer per string-kind** — all symbol/exchange/universe/query/status normalization routes through `domain/symbols.py` + `domain/normalize.py`. Grep gate: no `\.upper\(\)\.strip\(\)` or `\.strip\(\)\.upper\(\)` outside those two modules.
2. **Slippage only via `domain.trading_costs.apply_slippage`** — grep gate forbids inline `price * (1 ± slippage`.
3. **All money/quantity use `Money`/`Quantity`** — no raw `float` price through analytics fill math; ban `float(Decimal(str(...)))` round-trips.
4. **Constants live in `domain/constants/*`** — no magic backoff/timeout/rate literals in broker or analytics code; grep gate on numeric literals in `backoff`/`retry`/`_greeks`.
5. **One resilient reconnect seam** — `brokers/common/transport.ReconnectingTransport` is the only reconnect implementation; Dhan must not re-implement backoff.
6. **One OMS/TradingContext builder** — `application/oms/factory.create_trading_context` is the only constructor; no `create_trading_context` in `domain/`.
7. **No module-level mutable process state** — globals owned by `runtime/process_state.py`, injected at root.
8. **`ponytail:` comment on every intentional shortcut** naming its ceiling + upgrade path (per existing rule).

### 5.4 Guardrails to prevent recurrence

- **import-linter contracts** (already in `pyproject.toml`): promote the relaxed application→infrastructure rule to **CI-blocking**; add an explicit `domain` must-not-import `application` check (catches the `runtime_hooks` shim).
- **Grep-based pre-commit hooks** for the literals in §5.3 (normalize/slippage/Money/backoff) — fail the commit with the file:line.
- **`__all__` discipline**: every module declares `__all__`; the `historical_data.py` stub pattern (docstring-only, empty `__all__`) is banned — modules are either real or deleted.
- **Architecture tests** in `tests/architecture/`: assert exactly one `create_trading_context` definition; assert `make_position_key` and `make_instrument_id` agree on suffix policy; assert Dhan & Upstox reconnect share `ResiliencePolicy`.
- **ADR template** (`docs/architecture/adr/`) required for any new broker/exchange/engine before code — prevents re-splitting (SMELL-4/6).
- **`graphify update .`** after every code change (existing rule) so the coupling graph stays current and future audits re-run cheaply.

---

## Cross-Reference
- Correctness/safety findings (F1–F9): [`PRIORITIZED-AUDIT.md`](PRIORITIZED-AUDIT.md)
- As-built map: [`CURRENT-STATE.md`](CURRENT-STATE.md)
- Target + migration: [`TARGET-STATE.md`](TARGET-STATE.md)

## Open domain-knowledge flags (do NOT guess)
- **ATR smoothing** (SMA vs Wilder) — which is correct for NSE strategy math? Quant must confirm before REF-5 collapse.
- **Suffix policy for `*-EQ`/`*-BE`** — keep in position keys or strip? Drives REF-1 key-format decision; affects reconciliation/storage bridging.
- **Risk-free rate** — `0.06` vs `0.065` divergence; confirm the canonical value for greeks/sharpe.
