# ADR-006: Deletion Strategy — No Compat/Shim/Transitional Layers

## Status
Accepted (Phase 0)

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
