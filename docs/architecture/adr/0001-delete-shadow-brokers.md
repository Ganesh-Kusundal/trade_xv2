# ADR-001: Delete orphaned shadow `brokers/` copies

- **Status:** Proposed
- **Date:** 2026-07-12
- **Deciders:** Architecture review

## Context
`brokers/providers/dhan/gateway.py` and `brokers/providers/dhan/orders.py` at the repo root are divergent
duplicates of `src/brokers/providers/dhan/gateway.py` / `src/brokers/providers/dhan/orders.py`. The root
copy imports `from tradex.runtime.capabilities import ...` and `from brokers.providers.dhan.connection`,
a parallel implementation. It is kept from shadowing `src/` only by
`src/brokers/_bootstrap.py`, which force-inserts `src/` first on `sys.path` and deletes
a wrongly-cached `domain` module. A regression in path order would silently import the
stale copy — a real-money hazard.

## Decision
1. Delete `brokers/providers/dhan/gateway.py` and `brokers/providers/dhan/orders.py`.
2. Keep `_bootstrap.py` for now (it protects against other shadowed editable installs)
   but add a test that `import brokers.providers.dhan.gateway` resolves to `src/brokers/providers/dhan/gateway.py`.
3. Grep the whole repo for any import of the root `brokers.providers.dhan.gateway` / `brokers.providers.dhan.orders`;
   none should remain (verified during baseline).

## Consequences
- Positive: removes a silent shadowing landmine; one source of truth for Dhan gateway.
- Negative: if an external tool pointed at the root copy, it breaks — none found.
- Neutral: `_bootstrap.py` stays as a guard rail.

## Validation
- Test: `tests/architecture/test_no_shadow_brokers.py` asserts the resolved `__file__`
  of `brokers.providers.dhan.gateway` starts with `src/`.
- CI: import-linter contract forbids `brokers.providers.dhan.gateway` resolving outside `src/`.
