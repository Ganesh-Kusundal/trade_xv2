# Refactoring Roadmap & Migration Plan — TradeXV2

**Principle (from Phase 0 brief):** understand before changing; prefer *move/merge/delete*
over new abstractions; optimise for 5–10 year evolution; every phase gated by tests and
approval. No code is changed until this plan is approved.

Each phase: **Objective · Files · Risk · Tests · Rollback · Validation**.

---

## P0 — Guardrail truthfulness (precondition for everything)
- **Objective:** make the architecture guardrails *truthful* so future refactors are
  measurable.
- **Files:** `tests/test_architecture.py`, `.import-linter.ini` (enable internal-import
  analysis or convert V1 lazy imports), `brokers/common/adapter_factory.py`,
  `brokers/common/oms/margin_provider.py`, `brokers/common/infrastructure.py`.
- **Risk:** Low. Mechanical.
- **Tests:** `tests/test_architecture.py` must go green; add an import-linter contract that
  analyses in-function imports.
- **Rollback:** revert the 3 files; guardrail stays red (documented).
- **Validation:** `pytest tests/test_architecture.py` green; `lint-imports` red on V1 until
  fixed (then green). See ADR-001.

## P1 — Broker selection via registry (kills D1)
- **Objective:** `brokers.common` never names `dhan`/`upstox`; adapters self-register by
  capability.
- **Files:** `brokers/common/registry.py`, `broker_port.py`, `adapter_factory.py`,
  `infrastructure.py`, `oms/margin_provider.py`; each broker `capabilities.py` registers.
- **Risk:** Medium (changes bootstrap). Mitigated by capability manifest already present.
- **Tests:** existing `BrokerContractSuite`; new test asserting `common` imports zero
  broker-specific symbols (static check).
- **Rollback:** feature-flag the registry; keep lazy-import path behind flag during rollout.
- **Validation:** fitness test green; a new broker can be added by dropping an adapter
  package only.

## P2 — Domain consolidation (kills D3, D9, D10, D14, D16)
- **Objective:** one source of truth for domain objects; delete `domain.aggregates`.
- **Files:** `src/domain/aggregates/*` (delete), migrate refs to `entities/instruments/options`;
  split `capability_manifest.py`; unify indicators; finish shim removal; delete `markets/`,
  empty `brokers/runtime/`.
- **Risk:** Medium (wide reference surface). Mitigated by deprecation warnings already in place.
- **Tests:** `test_domain_single_source.py`-style; full `src/domain` suite; grep gate for
  `domain.aggregates`.
- **Rollback:** `domain.aggregates` restored from git; shims temporarily re-added.
- **Validation:** zero imports of `domain.aggregates`; zero shim imports; domain tests green.

## P3 — Shrink & split `brokers` (kills D2, D5, D14)
- **Objective:** `brokers.common` = broker-agnostic core only; move orchestration out.
- **Files:** extract `router`, `stream_orchestrator`, `historical_coordinator`,
  `provenance`, `intelligent_market_gateway` → `application` / promoted `market_data` /
  `infrastructure`. Promote `market_data/` to a real package. Fold `plugins`/`providers`.
- **Risk:** High (touches runtime + API + CLI wiring).
- **Tests:** integration parity gate (`runtime/parity_gate.py`, `parity_config.py`); contract
  tests per broker.
- **Rollback:** keep old modules behind re-export shims for one release.
- **Validation:** `brokers` LOC < ~25k; `common` < ~12k; import-linter `brokers-common-*`
  contracts tighten (remove carve-outs).

## P4 — Port-extract OMS & analytics boundaries (kills D4, D7, D8, D12)
- **Objective:** `application.oms`/`analytics` depend on abstractions, not `infrastructure`/
  concrete `datalake`.
- **Files:** extract `event_publisher`, `persistence`, `metrics`, `state_machine` ports into
  `domain/ports`; inject impls; break `cli/services` cycle via `CapitalProvider` port;
  route `analytics → datalake` through a port; move event types to `domain`.
- **Risk:** Medium-High.
- **Tests:** OMS unit tests with fakes (`src/domain/tests/_fakes.py`); import-linter
  `application-infrastructure-separation` carve-outs removed progressively.
- **Rollback:** restore `ignore_imports` carve-outs.
- **Validation:** import-linter contract passes *without* carve-outs for the migrated modules.

## P5 — Single data/normalization boundary (kills D6)
- **Objective:** broker → canonical domain VO once; replay is a `DataProvider`.
- **Files:** `brokers/common` normalizers (canonical), `datalake/normalize.py` (reuse),
  `analytics` consumes VOs; implement replay as `DataProvider` impl.
- **Risk:** Medium.
- **Tests:** golden-packet tests (`scripts/generate_depth_golden_packets.py` → suite);
  replay parity tests.
- **Rollback:** keep analytics transforms behind adapter.
- **Validation:** one normalization path; strategies can't distinguish replay vs live.

## P6 — SDK & tooling polish (kills D11, D13, D15, D17, D18)
- **Objective:** one composition root, one SDK facade, consolidated ports, productized tooling.
- **Files:** `runtime/trading_runtime_factory` decoupled from `cli`; add `tradexv2` facade;
  consolidate gateway ports; fold `scripts/` into commands/`tooling`; env flags → config.
- **Risk:** Low-Medium.
- **Tests:** SDK smoke tests; CLI/API parity.
- **Rollback:** keep legacy entry shims.
- **Validation:** developer can `tradexv2.connect("dhan").instrument("X").buy()`; single DI root.

---

## Sequencing & gates
```
P0 ─▶ P1 ─▶ P2 ─▶ P3 ─▶ P4 ─▶ P5 ─▶ P6
(green    (registry) (domain) (shrink) (ports) (data) (SDK)
 guardrails)
```
- **No phase starts until the prior phase's validation is green.**
- **P0 is a hard precondition**: without truthful guardrails, later phases cannot be
  verified and risk regressions that import-linter currently masks.
- Each phase ships behind feature flags / shims where runtime impact is high (P1, P3).

## Effort estimate (rough)
- P0: S · P1: M · P2: M · P3: L · P4: L · P5: M · P6: M.
- P3 + P4 are the highest-risk and should be done by the Broker Platform + OMS divisions
  with Integration validation after each.
