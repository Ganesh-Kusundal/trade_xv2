# ADR-022: State store invariant (single-writer)

**Status:** Accepted (interim)  
**Date:** 2026-07-12  
**Related:** TOS-P7-005, DR-I7

## Context

OMS/journal state lives in process-local SQLite files (`market_data/*.sqlite`) with `flock` / file locks. DuckDB is analytics-oriented. Horizontal multi-writer scaling is not supported today.

## Decision

Until a dedicated multi-process store is selected:

1. **Single-writer process invariant:** one trading runtime process owns order/position/journal files.
2. **No silent multi-writer:** do not run two live OMS processes against the same SQLite paths.
3. **Future evaluation:** Redis/Postgres for shared state is out of scope for this program phase; track as a separate capacity initiative.

## Consequences

- Deploy as single active writer (+ read replicas only for analytics lake).
- Chaos/recovery tests assume one process restarts and reloads from ledger/journal.
