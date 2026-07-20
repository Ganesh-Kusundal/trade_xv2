# Code Standards — TradeXV2 / TradeX Trading OS

> Part of the **Six-File Context System**. These are the implementation conventions the
> agent must follow so output stays consistent across sessions and units. Grounded in
> `pyproject.toml` quality gates, import-linter contracts, and the existing codebase.

## 1. Language & Tooling

- **Python** backend (target: 3.11+). Strict typing — mypy in CI (strict-ish).
- **TypeScript/React** frontend in `web/` is **planned but not yet implemented**
  (`web/` currently holds only `.env.example`). The conventions below apply
  once the SPA is scaffolded; do not reference `web/` source files as if they
  exist today.
- Format/lint: **ruff** (Python), **Prettier/ESLint-equivalent via Vite** (TS). Run the
  project's pre-commit (`ruff`, `mypy`, `gitleaks`, arch tests) before committing.
- Quality gates (from `pyproject.toml`): ruff, mypy, bandit, safety, coverage
  `fail_under=80` (brokers ≥85, oms ≥90), mutmut 90%.

## 2. Python Conventions

- **Ports before concretes**: depend on `domain.ports` Protocols, inject implementations
  in `runtime/`. No `import` of a concrete broker/infra class outside `runtime/`.
- **No `getattr` reach-throughs** across layers — use explicit ports (see `RiskGate`).
- **One Callable, not hardcoding**: transports/credentials passed as `Callable`
  (e.g. `make_gateway_submit_fn`), never inlined.
- **Domain model on the write path**: build typed `Order`/`Position`/`Trade` entities;
  avoid returning raw dicts where a typed model exists.
- **`ponytail:` comments** mark intentional shortcuts and name their ceiling/upgrade path.
- **File size**: ADR-011 enforces a per-file LOC cap; split god-facades
  (e.g. `UpstoxBroker`) into focused modules.
- **No mock/fake data** in production code (integration tests only).
- **Mock policy:** tests may use real protocol fakes (e.g. `FakeHttpClient`,
  plain stub objects with only the attributes the code reads) but **must not**
  use `MagicMock` / `unittest.mock.patch` over safety-critical logic. The
  order/gate/parity path (live-order authority, extended-order executors,
  parity gate) is **mock-free by CI enforcement**
  (`tests/architecture/test_no_mock_in_integration.py`) — a mock that silently
  returns `None` for an unauthorized order is the exact class of real-money bug
  to avoid. A test that needs a double on that path must use a real fake, not a
  `MagicMock`.

## 3. Layering & Imports

- Follow the dependency rule in `architecture.md` §3. import-linter contracts in
  `pyproject.toml` are CI-blocking for rules 1–4. Do not add `ignore_imports` exceptions
  casually — each one documents a known violation; prefer fixing the violation.
- `domain/` imports only stdlib + itself.

## 4. File Organization

- New broker/exchange code goes in `src/plugins/` (or its own entry-point package),
  registered via `tradex.brokers` / `tradex.exchanges`, NOT as a first-class `src/` layer.
- Adapters live in `infrastructure/`; use-cases in `application/`; entities/ports in
  `domain/`. Composition in `runtime/`.
- Keep the repo root clean — no ad-hoc `run_*.sh` / `pytest_runner*.py` (G8).

## 5. TypeScript / Web Conventions (`web/`)

> **Status:** The Web SPA is not yet implemented. `web/` contains only
> `.env.example`. The conventions below are the target for when the SPA is
> scaffolded; they describe a planned interface, not existing source.

- React 18 function components + hooks. State via hooks; data via `src/api` + generated
  client (`scripts/gen_openapi.py` → `src/api/generated.ts`). Do not hand-edit generated
  types. Regenerate with `npm run api:generate`.
- Typed models in `web/src/types.ts`; reusable UI in `web/src/components`; feature hooks
  in `web/src/hooks`.
- `npm run build` = `tsc --noEmit && vite build` must pass. `npm test` = Vitest.
- No new UI component library beyond current deps (React, react-dom, react-router-dom).

## 6. Testing

- **Integration tests only** — verify real behavior with real components/dependencies.
  No mocking or dummy data (per project rules).
- Tests live under `tests/` mirroring `src/`; architecture tests under `tests/architecture/`.
- New logic leaves one runnable check behind (assert-based demo/self-check or a small
  test file). Trivial one-liners need no test.
- **Broker regression permanence:** every confirmed live-broker bug must add a permanent
  regression case to the broker manifest (`tests/integration/brokers/{dhan,upstox}/regression/manifest.py`).
  CI gates in `test_coverage_manifest.py` enforce P0 coverage — do not remove cases without an ADR.

## 7. Docs & Graph Sync

- After modifying code files under `src/`, run `graphify update src` to keep `src/graphify-out/` current.
- Keep `context/*.md` and `docs/architecture/*` in sync with implementation. If a change
  alters architecture/scope/standards, update the relevant file before continuing.
