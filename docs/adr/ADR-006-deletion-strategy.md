# ADR-006: Deletion Strategy — No Compat/Shim/Transitional Layers

## Status
Superseded (2026-07-10 audit — see docs/architecture/trading-os/TRADING_OS_BLUEPRINT_V2_PART6.md §4)

## Context
Previous refactors accumulated facades, adapter shims, and "deprecated" wrappers
that kept old broker-gateway code alive and doubled the maintenance surface.

## Decision
Each phase **deletes** its old counterpart in the same PR. There are no
transitional packages, shim modules, compat re-exports, or `DeprecationWarning`
wrappers. When `domain/` moves to `src/domain/`, the old `domain/` is removed;
when `brokers/dhan/gateway.py` is re-expressed as a plugin, it is deleted, not
wrapped.

## Consequences
- Simple, single-source-of-truth code.
- Larger per-PR diffs, but no long-lived dead code.
- Requires keeping the build green within each PR (full test pass before merge).

## Superseded note

Verified against source during the 2026-07-10 architecture audit: this is
the most significant correction in that audit. This ADR says there are "no
transitional packages, shim modules, compat re-exports, or
`DeprecationWarning` wrappers" — but a grep found **58 files** across
`src/` containing exactly that pattern, including the entire
deliberately-maintained `tradex.runtime` facade package (a ~90-entry
backward-compat mapping with its own dedicated test file verifying the
deprecation warnings fire correctly) and the `InstrumentAggregate` alias
still emitting a live `DeprecationWarning` on every test run.

This is not drift — it is the opposite policy, adopted deliberately and
extensively. The actual, working policy in effect today is: **shims are
permitted for gradual migration, must emit `DeprecationWarning`, and
should have a tracked removal path.** Leaving this ADR's original
"Accepted" label in place while the codebase visibly and consistently does
the opposite makes it actively misleading, not just stale — a new engineer
(or AI agent) reading it would reasonably conclude shims are forbidden.
See `docs/architecture/trading-os/TRADING_OS_BLUEPRINT_V2_PART6.md` §4 for
the full reasoning and file count.
