# ADR-015: Execution Ledger as Authoritative Write Boundary

- **Status:** Accepted
- **Date:** 2026-07-11
- **Deciders:** Chief Architect, OMS/Execution lane

## Context

Order state today is split across `OrderManager` in-memory book, `SqliteOrderStore`, `EventLog`, and `ProcessedTradeRepository`. Paper, replay, and live paths partially share OMS but not one durable spine. Partial fills and UNKNOWN recovery depend on reconciliation detecting drift after the fact.

## Decision

1. **Execution ledger** (outbox + fill ingress) becomes the **authoritative write boundary** for all money-moving facts.
2. `OrderManager` routes intents through ledger `record_intent` / `record_outcome` / `record_fill` before returning to callers (record-then-submit already exists in `OrderLifecycle`).
3. **Portfolio and position reads** migrate to projections over ledger events; shadow-compare with current book until parity proven (TRANS-P5-031).
4. Paper, replay, live, and backtest `parity` mode use the **same command handlers** and ledger contract; mode differs only at clock, market source, and execution transport.

## Consequences

- Enables deterministic replay certification (`test_event_replay_determinism.py` as gate).
- Requires feature flag `TRADEX_LEDGER_AUTHORITY` for cutover (default off until shadow parity).
- Deprecates parallel truths in `PaperOrders` / duplicate books when usage hits zero.

## Alternatives rejected

- Big-bang delete `OrderManager` book — too risky without shadow period
- Event sourcing entire platform — YAGNI; ledger seam is sufficient

## Compliance

- Phase 5 tasks: TRANS-P5-030, TRANS-P5-031
- Acceptance: 24h replay fixture shadow parity = 0 drift