# ADR-003: Single configuration source

- **Status:** Proposed
- **Date:** 2026-07-12
- **Deciders:** Architecture review

## Context
Two parallel config systems exist: per-broker loaders in
`src/infrastructure/config/settings.py` (`SettingsLoaderBase`) and a central Pydantic
`AppConfig` in `src/config/schema.py:22` (`AppConfig.from_env()`, `TRADEX_` prefix).
They can drift, producing inconsistent runtime settings.

## Decision
`AppConfig` (Pydantic, `TRADEX_` env prefix) is the single source of truth. The
`infrastructure.config` loaders are deprecated and thin-re-export `AppConfig` during a
transition window, then removed. Profiles (`src/config/profiles/`) remain the
environment-selection mechanism.

## Consequences
- Positive: one validated config model; typos caught at load; no drift.
- Negative: call sites using the old loaders must migrate (mechanical).
- Cost: transition re-exports add a small shim, deleted in Phase 5 (P5-4).

## Validation
- A test asserts every setting previously read via `SettingsLoaderBase` is present in
  `AppConfig`. Grep shows zero remaining direct `SettingsLoaderBase` usage post-migration.

## Status (contract present 2026-07-12)
- **Status:** Accepted (contract); implementation deferred to G4 / P5-4.
- The single config source (`AppConfig`, Pydantic, `TRADEX_` env prefix) already
  exists at `src/config/schema.py`. The `infrastructure.config` loaders remain the
  legacy path to be deprecated and migrated in P5-4.
- No new code added in this milestone; this ADR records that the target contract is
  already in place and the remaining work is the mechanical migration (P5-4).
