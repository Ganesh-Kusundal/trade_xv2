# Behavioral Test Suite — Design Spec

**Date:** 2026-07-21  
**Status:** Approved for implementation  
**Scope:** Full pyramid (`tests/**`, 877 files)

## Problem

Many runtime tests assert implementation details (AST scans, source substrings, private fields, mock delegation) instead of business behavior. Refactors that preserve external behavior break tests; static architectural rules are duplicated in pytest.

## Design principle

> If I rewrite the implementation tomorrow but keep the same external behavior, would I keep this test?

| Layer | Tests what | Tool |
|---|---|---|
| Unit | Domain rules, pure mappers, public gateway contracts | pytest |
| Component | Application services with port fakes | pytest |
| Integration | Multi-module collaboration, paper/sandbox/live | pytest |
| E2E / Chaos | Full process, fault injection | pytest |
| Architecture (runtime) | Fail-closed prod config, parity drift, cert schema | pytest |
| Structure / layering | Imports, LOC, banned APIs, grep ratchets | import-linter, ruff, CI scripts |

## Disposition vocabulary

- **KEEP** — behavioral; survives internal refactor
- **REWRITE** — real contract; replace internals with observables
- **MOVE_STATIC** — enforce via lint/CI, delete pytest wrapper
- **MOVE_LAYER** — wrong pyramid tier (e.g. UI mocks in component)
- **DELETE** — duplicate of another gate; no residual value

## Preserve list (never weaken without replacement)

See [`ledgers/test-preserve-list.md`](ledgers/test-preserve-list.md).

## Phase deliverables

| Phase | Outcome |
|---|---|
| 0 | Ledger + this spec + implementation plan |
| 1 | import-linter extended; CI scripts; architecture suite ~50% smaller |
| 2 | `tests/unit/domain/**` public-API only |
| 3 | Broker websocket/depth via golden + observables |
| 4 | OMS behavioral fakes; UI mocks → unit |
| 5 | Integration de-mock; e2e paper; chaos source cleanup |

## Success criteria

1. Ledger covers 100% of test files
2. No pytest whose sole assertion is AST/source layout
3. Money-safety + regression manifests + BrokerContractSuite green
4. Pyramid placement matches `tests/README.md`

## References

- [`tests/README.md`](../../tests/README.md)
- [`context/code-standards.md`](../../context/code-standards.md)
- Ledger: [`ledgers/test-disposition-phase0.md`](ledgers/test-disposition-phase0.md)
