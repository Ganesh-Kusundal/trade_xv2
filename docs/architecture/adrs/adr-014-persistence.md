# ADR-014: Persistence Stack

- **Status:** Accepted
- **Date:** 2026-07-10
- **Deciders:** Chief Quant Architect, Platform Engineering Director

## Context

The proposed Trading OS diagram listed `Redis / Memory Cache`, `DuckDB /
PostgreSQL`, and `Parquet` as the persistence layer. The implemented
`Trade_XV2` codebase uses a different, concrete stack:

- **Cache:** in-memory cache (`infrastructure/cache.py`) is primary; a Redis
  cache backend exists (`infrastructure/cache_redis.py`) but is optional.
- **Relational / analytics:** **DuckDB** (`infrastructure/db/duckdb_pool.py`)
  over a **Parquet** lake (`.datalake` curated layout) is the analytics store.
- **Execution ledger / order store:** **SQLite**
  (`infrastructure/persistence/sqlite_execution_ledger.py`,
  `sqlite_order_store.py`).
- **PostgreSQL is not present.**

## Decision

- The canonical persistence stack is: **SQLite** (execution ledger + order
  store) + **DuckDB** (analytics, via Parquet lake) + **Parquet** (data lake).
- **PostgreSQL is deferred.** It is only adopted if/when a multi-worker,
  shared-state API deployment creates a real need (e.g. multiple API processes
  sharing order/position state). Until then, SQLite + DuckDB + Parquet are
  sufficient and avoid operational overhead.
- Redis remains an optional cache backend, not a required dependency.

## Consequences

- Documentation matches the deployed stack.
- A future Postgres migration is a scoped Platform Engineering task, gated by a
  concrete multi-worker requirement (not speculative).
