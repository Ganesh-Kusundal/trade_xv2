# Prioritized Action Plan

## Top 20 risks

1. Backtest defaults bypass OMS risk.
2. Live/paper/replay/backtest do not share one authoritative execution/PnL spine.
3. Ambiguous order POST retries can duplicate live orders.
4. Pending exposure is not reserved atomically.
5. Reconciliation omits fills, prices, fees, multipliers, and PnL.
6. Invalid or stale market data can become a valid-looking input.
7. Account/balance failures can become zero or empty state.
8. Feature failures can fall back to raw/neutral inputs.
9. Scanner correlation identity can collide.
10. Fill dedupe/overfill handling is incomplete.
11. Paper uses synthetic data and a separate OMS-like flow.
12. Dhan and Upstox reconnect mechanisms diverge.
13. Raw broker dicts/statuses cross domain boundaries.
14. Synchronous event dispatch can block the feed.
15. Queue drops have no resync/checkpoint protocol.
16. SQLite/process-global state has no enforced deployment topology.
17. Unsigned token webhook accepts sensitive material.
18. Plaintext token fallback is allowed.
19. Shared API key is not RBAC; admin claims are inconsistent.
20. CI and architecture/security gates can pass without scanning or running the intended code.

## Top 20 improvements

1. Define the immutable execution/event contract.
2. Build one durable execution ledger/projector.
3. Make unknown broker writes reconcile-before-retry.
4. Add atomic pending-order reservations.
5. Enforce full economic reconciliation.
6. Reject/quarantine invalid and stale market data.
7. Make feature failure fail closed.
8. Make candidate identity mandatory and deterministic.
9. Normalize all broker output through the ACL.
10. Use one transport/resilience owner.
11. Convert Paper to a fill model behind the shared OMS.
12. Remove replay/paper shadow PnL.
13. Add event sequence, schema version, and resync.
14. Separate liveness, readiness, and tradability.
15. Require encryption and external secret management in production.
16. Add signed webhooks and scoped RBAC.
17. Make audit append durable and transactional with intent.
18. Repair CI paths and make critical gates blocking.
19. Establish latency, queue, freshness, and reconciliation budgets.
20. Gate strategy promotion on point-in-time and walk-forward evidence.

## Quick wins: 1–2 days

- Mark research-only backtest results visibly and reject parity claims from `PURE_SIM`.
- Add a repository-root helper to architecture/security tests so they scan `src/`.
- Disable automatic retry for ambiguous order writes.
- Make readiness fail when required broker streams, encryption, or reconciliation are unknown.
- Add explicit `UNKNOWN`/`STALE` states instead of empty/zero fallback in account and market-data contracts.
- Correct CI paths that reference pre-`src/` layouts.

## Medium term: 1–4 weeks

- Implement event/order/fill identity and atomic risk reservations.
- Build full economic reconciliation and duplicate/overfill tests.
- Complete broker ACL translation and typed contract assertions.
- Consolidate reconnect and request policies.
- Route Paper and replay through shared execution/projection components.
- Add WebSocket queue metrics, sequence gaps, and client resync.
- Replace webhook/API-key authorization with signed requests and scoped roles.

## Long term: 1–6 months

- Deploy a durable partitioned execution ledger and checkpointed projections.
- Migrate brokers to thin wire adapters and delete mirrored gateway ownership.
- Establish real-broker sandbox/recovery drills and production-like performance tests.
- Add strategy registry/promotion governance with reproducible data and cost assumptions.
- Scale market data and analytics independently from single-writer order mutation.

## Stop/go rule

No live-capital increase is justified until the first seven risks are closed with executable evidence. “The service stayed up” is not evidence of order correctness, position correctness, or safe recovery.
