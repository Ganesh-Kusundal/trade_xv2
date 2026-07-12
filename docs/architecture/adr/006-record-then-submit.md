# ADR-006: LedgerOutbox — Record-Then-Submit Pattern for Order Durability

## Status

Accepted

## Context

Orders placed with a broker must be durable: if the process crashes between the broker accepting the order and the OMS recording it, the system would lose track of live positions. The original design submitted to the broker first and recorded after, creating a window for data loss.

## Decision

Implement the **LedgerOutbox** pattern (`application/oms/ledger_outbox.py`) with a **record-then-submit** flow:

1. **Record intent** — persist the order intent to the SQLite order store *before* submitting to the broker.
2. **Submit to broker** — send the order to the broker via the execution adapter.
3. **Confirm or reject** — on broker acknowledgment, update the persisted record with the broker order ID and status. On failure, mark the intent as rejected.

The critical invariant: `persist_intent_then_submit` is called by `OrderLifecycle.submit_to_broker`, and the function must contain `record_intent` as its first step.

### Ledger authority

When `TRADEX_LEDGER_AUTHORITY=1`, the execution ledger is the source of truth for position reconciliation. The `ledger_authority_enabled` function defaults to disabled (`"0"`), and the ledger authority policy (`application/oms/ledger_authority.py`) is a pure policy with no infrastructure imports.

## Consequences

**Positive:**
- Crash recovery can reconcile broker state with recorded intents.
- No orphaned live positions that the OMS doesn't know about.
- The ledger authority flag allows gradual rollout of ledger-based reconciliation.

**Negative:**
- One additional write before broker submission (latency cost, ~1ms for SQLite WAL).
- Rejected intents must be cleaned up to avoid clutter.

## Enforcement

- `tests/architecture/test_ledger_outbox_boundary.py` — verifies `persist_intent_then_submit` is called in `submit_to_broker`, and that `record_intent` is in the outbox source
- `tests/architecture/test_composition_root.py` — `test_ledger_policy_defaults_off`
