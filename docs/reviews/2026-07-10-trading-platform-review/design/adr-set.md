# Architecture Decision Records

## ADR-001: One execution ledger is the economic source of truth

**Status:** Proposed  
**Decision:** Persist order intents, submission outcomes, fills, position transitions, cash/PnL transitions, and reconciliation results in one account/strategy-partitioned execution ledger. Projections are rebuildable read models.  
**Reason:** Current OMS, Paper, replay, and backtest state can diverge. `EventLog`, `ProcessedTradeRepository`, and `SqliteOrderStore` each persist only part of the lifecycle.  
**Rejected:** Making every analytics object independently authoritative or introducing platform-wide event sourcing before the economic ledger exists.

## ADR-002: Replay preserves identity; re-execution is a separate operation

**Status:** Proposed  
**Decision:** Recovery replay rebuilds projections from persisted events while preserving event IDs and checkpoints. Research re-execution creates a new run ID and never mutates live account state.  
**Reason:** Existing processed-trade dedupe can suppress historical events during restart reconstruction.  
**Rejected:** Reusing one idempotency path for both recovery and new simulation.

## ADR-003: Ambiguous broker writes are `UNKNOWN`

**Status:** Proposed  
**Decision:** Timeouts, connection loss, and response parse failures after a write become `UNKNOWN`. No generic retry occurs until broker reconciliation establishes absence or identity.  
**Reason:** A broker may accept an order after the client loses the response.  
**Rejected:** Retrying all POSTs based on transport exception.

## ADR-004: Broker ACL is mandatory

**Status:** Proposed  
**Decision:** Raw payloads, broker status strings, wire prices, timestamps, and segment codes terminate in broker adapters. Domain/application receives typed entities and normalized errors only.  
**Reason:** Current raw dict leakage and duplicated mapping make broker differences observable outside adapters.  
**Rejected:** Expanding gateway facades or allowing `dict` compatibility returns indefinitely.

## ADR-005: Market-data ingestion has one owner

**Status:** Proposed  
**Decision:** Broker transport → validated canonical event → durable/sequence-aware stream → consumers. API/UI clients submit subscription intent; they do not invoke broker stream lifecycle directly.  
**Reason:** Current broker publishers, `StreamOrchestrator`, and API feed wiring can duplicate ingestion and make subscription teardown global.  
**Rejected:** Adding more per-client broker subscriptions.

## ADR-006: Readiness is tradability, not process liveness

**Status:** Proposed  
**Decision:** Separate liveness, service readiness, and trading readiness. New entries require authenticated broker state, fresh market/order/account data, durable ledger, clean reconciliation, valid secrets, and authorized control state.  
**Reason:** Current `/healthz`, `/readyz`, and production readiness paths can disagree or report non-enforcing failures.  
**Rejected:** Treating a connected process or socket as tradable.

## ADR-007: Paper is a fill model, not an alternate OMS

**Status:** Proposed  
**Decision:** Paper consumes the same order intent, risk, fill, projection, and reconciliation contracts as live. Only its event source and fill model are different.  
**Reason:** Current Paper has internal orders/trades/positions plus analytics session state.  
**Rejected:** Maintaining separate paper behavior as a “realistic enough” approximation.

## ADR-008: Scale execution by partition ownership

**Status:** Proposed  
**Decision:** Account/strategy partitions have one writer lease and ordered event processing. Market-data normalization and analytics can scale independently.  
**Reason:** SQLite and mutable process-global state cannot safely support horizontal order mutation.  
**Rejected:** Adding API workers without a ledger partition model.
