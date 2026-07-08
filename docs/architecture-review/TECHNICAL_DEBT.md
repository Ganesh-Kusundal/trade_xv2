# Technical Debt Register — TradeXV2

Ranked by risk-to-evolution. Each item: location, symptom, impact, recommended fix
(cross-referenced to `REFACTORING_ROADMAP.md` phase). Debt IDs match ADR/roadmap.

## Critical (blocks clean evolution)
- **D1 — Hidden layer violation `brokers.common → brokers.dhan/upstox`**
  `brokers/common/adapter_factory.py:35-36`, `brokers/common/oms/margin_provider.py:39`,
  `brokers/common/infrastructure.py:13-14`. Lazy imports inside functions; invisible to
  `lint-imports` (top-level only) but caught by `tests/test_architecture.py` (currently
  **FAILING**). Impact: broker-agnosticism is a lie; adding a broker touches `common`.
  Fix: registry/plugin lookup by capability (ADR-001, Roadmap P1).
- **D2 — `brokers/` god-package (86k LOC / 531 files)**
  `common` has 39 top-level modules spanning orchestration, routing, historical,
  provenance, intelligent-gateway. Impact: every change risks the whole broker surface;
  tests slow; onboarding hard. Fix: split per ADR-004 (Roadmap P3).
- **D3 — Parallel domain models (`entities` vs `aggregates`)**
  `OptionChain`, `Instrument`, `Order`, `Position` defined twice; `domain.aggregates`
  deprecated (emits `DeprecationWarning`) yet still imported. Impact: ambiguity about
  source of truth; drift risk. Fix: consolidate to `entities/instruments/options`
  (Roadmap P2).

## High
- **D4 — OMS bypasses ports (`application.oms.* → infrastructure.*`)**
  30+ `ignore_imports` in `application-infrastructure-separation`. Impact: OMS not
  unit-testable without infra; layering contract is cosmetic. Fix: extract ports, inject
  (Roadmap P4).
- **D5 — `market_data` package dismantled**
  No Python package; responsibility scattered (`brokers.common`, `infrastructure`,
  `datalake`, `analytics`, `src/domain/quotes`). Impact: no owner, duplicated
  normalization. Fix: promote `market_data/` (Roadmap P3/P5).
- **D6 — Duplicate normalization**
  `brokers.common` normalizers + `datalake/normalize.py` + `analytics` transforms.
  Fix: single broker→domain-VO normalization boundary (Roadmap P5).
- **D7 — `cli/services` import cycle**
  `broker_service → oms_setup → capital_provider → broker_service`. Fix: move
  `CapitalProvider` to domain/application port (Roadmap P4).

## Medium
- **D8 — `analytics → concrete datalake.gateway/research`**
  import-linter `analytics-no-datalake-concrete` carve-outs. Fix: route through
  `datalake` port/adapter (Roadmap P4).
- **D9 — God file `src/domain/capability_manifest.py` (1279 LOC)**
  Fix: split per capability group (Roadmap P2).
- **D10 — Dual indicator implementations**
  `domain/indicators` + `analytics/indicators`. Fix: single source in domain (Roadmap P2).
- **D11 — Multiple composition mechanisms**
  `infrastructure.di.Container` + `runtime.composition.create_api_event_bus` +
  `brokers/common/registry`. Fix: one canonical composition root (Roadmap P1/P6).
- **D12 — Events defined in `infrastructure`, not `domain`**
  `infrastructure/event_bus/event_types`. Fix: move to `domain` + bus as port (Roadmap P4).
- **D13 — Two gateway port files / naming**
  `domain/ports/broker_gateway.py` = `OrderTransportPort`; `BrokerGateway`/`MarketDataGateway`
  in `protocols.py`. Fix: consolidate naming (Roadmap P6).

## Low
- **D14 — Dead/empty packages:** `markets/` (empty), `brokers/runtime/` (0 files),
  `domain.aggregates` (deprecated), near-empty `plugins/` (77 LOC), `providers/` (298 LOC
  overlapping `domain/providers` + `brokers/common/registry`). Fix: delete/fold (Roadmap P2/P3).
- **D15 — 35 `scripts/*.py` procedural sprawl**
  Diagnostics/verification/migration not productized. Fix: fold into commands or a
  `tooling` package; keep only CI-facing scripts (Roadmap P6).
- **D16 — Shims `brokers.common.core.*`**
  Enforced-removed by fitness test (passing). Track to zero (Roadmap P2).
- **D17 — No top-level `tradexv2` SDK facade**
  Discovery friction. Fix: add facade in P6.
- **D18 — Env-flag-gated behaviour**
  `ENABLE_INTELLIGENT_GATEWAY`, `ORCHESTRATOR_DRY_RUN` as side-effects. Fix: explicit config
  (Roadmap P6).

## Debt metrics
- Prod `.py` files: 930 · Test `.py` files: 597 (~39% test files).
- `brokers` test ratio: 207/534 (~39%) — adequate coverage *on a package that should be
  smaller*.
- Architecture fitness test: **2 failing** (D1). `lint-imports`: 0 (masked by D1).
