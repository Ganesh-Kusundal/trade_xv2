# ADR-003: SQLite WAL for OMS Order/Execution Persistence

## Status

Accepted

## Context

The OMS (Order Management System) needs durable persistence for order intents, execution records, and ledger entries. The persistence layer must support:

- Single-process access (no multi-worker requirement today).
- Crash recovery (WAL mode for durability).
- Low operational overhead (no external database server).
- Analytical queries over order/execution history.

The alternatives considered were PostgreSQL (operational overhead, no multi-worker need), in-memory only (no crash recovery), and file-based (concurrent access issues).

## Decision

Use **SQLite with WAL (Write-Ahead Logging)** mode for:

- **Order store** (`infrastructure/persistence/sqlite_order_store.py`) — persists order intents and lifecycle state.
- **Execution ledger** (`infrastructure/persistence/sqlite_execution_ledger.py`) — records execution events for reconciliation and audit.

SQLite is the canonical persistence backend for single-process deployments. PostgreSQL is deferred until a concrete multi-worker, shared-state requirement emerges (see ADR-014-persistence).

## Consequences

**Positive:**
- Zero operational overhead (embedded database).
- WAL mode provides crash-recovery durability.
- Single-file database simplifies backup and portability.
- Sufficient for single-process trading with thousands of orders per day.

**Negative:**
- Not suitable for multi-worker deployments (deferred to PostgreSQL when needed).
- Write contention under extreme concurrency (mitigated by the OMS lock discipline in `test_stream_oms_lock_discipline.py`).

## Enforcement

- `tests/architecture/test_stream_oms_lock_discipline.py` — PositionManager/OrderManager hold locks around book mutations
- `tests/architecture/test_ledger_outbox_boundary.py` — ledger outbox record-then-submit pattern
- `tests/architecture/test_fail_closed_capital_paths.py` — OMS lifecycle persistence assertions
