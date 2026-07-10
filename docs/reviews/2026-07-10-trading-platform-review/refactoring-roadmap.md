# Refactoring Roadmap

The roadmap starts with ownership and invariants. It intentionally avoids a list of isolated guards because more than two local fixes would leave the systemic state and contract problem intact.

## Target repository structure

```text
src/
  domain/
    orders/ positions/ portfolio/ instruments/ events/ ports/
  application/
    decision/ risk/ execution/ reconciliation/ control_plane/
  market_data/
    ingestion/ normalization/ storage/ replay/
  brokers/
    common/
      acl.py transport.py resilience.py registry.py contracts/
    dhan/
      wire.py auth.py adapters/
    upstox/
      wire.py auth.py adapters/
    paper/
      wire.py fill_model.py
  analytics/
    features/ strategies/ scanners/ research/
  infrastructure/
    event_store/ projections/ observability/ secrets/
  interface/
    api/ ui/
  runtime/
    composition_root.py
```

## Phase 0 — launch blockers (1–2 weeks)

1. Freeze unattended live trading and label `PURE_SIM` outputs as research-only.
2. Define immutable contracts for market event, signal decision, order intent, submission outcome, fill, position transition, reconciliation discrepancy, and readiness.
3. Fail closed on invalid/stale/missing market data, account reads, feature failures, and unknown broker state.
4. Make order writes operation-aware: no automatic retry for ambiguous non-idempotent POST; reconcile first.
5. Add atomic pending-order risk reservations and reject overfills/duplicate fills.
6. Require full economic reconciliation before new entries.
7. Replace unsigned webhook token ingestion, plaintext secret fallback, and shared-key-only authorization with signed/RBAC controls.
8. Make CI path checks and security/type/architecture gates blocking; distinguish not-run from passed.

## Phase 1 — one execution spine (2–4 weeks)

1. Create the durable execution ledger and projector for orders, fills, positions, cash, and PnL.
2. Route live, paper, replay, and backtest through the same decision → intent → outcome → fill → projection logic.
3. Make event identity, sequence, event time, receipt time, and schema version mandatory.
4. Move fill/slippage/fee/intrabar policies into explicit mode configuration captured in every result.
5. Remove replay/paper shadow PnL and symbol-by-symbol portfolio merging.

## Phase 2 — broker kernel migration (1–2 months)

1. Treat `domain.ports.BrokerAdapter` as the only external contract.
2. Complete `common/acl.py` so no raw dict/status/string crosses the boundary.
3. Make one policy-driven transport own retries, reconnect, backoff, timeout, and metrics.
4. Migrate Dhan first, prove parity with contract and reconnect tests, then migrate Upstox.
5. Reduce each broker to wire maps, auth-specific behavior, decoders, and capability data.
6. Enroll Paper as a transport/fill model behind the same contract.
7. Collapse duplicate use-case/extension implementations.

## Phase 3 — operational scale (1–6 months)

1. Partition the execution ledger by account/strategy and define single-writer ownership.
2. Add durable queues/checkpoints and client resync for market-data/WebSocket consumers.
3. Replace SQLite only after the partition/ledger contract is proven.
4. Build controlled broker-failure, restart, network-ambiguity, stale-data, and reconciliation drills.
5. Establish latency/throughput/error budgets and capacity tests as blocking release gates.
6. Add strategy promotion controls: walk-forward, out-of-sample, cost sensitivity, drawdown limits, and reproducible artifacts.

## Exit criteria

Live enablement requires all P0 controls green in a real broker read-only/sandbox environment, a restart/recovery drill with no state divergence, no unresolved reconciliation discrepancy, no stale-data decision, and an explicit emergency-exit policy.
