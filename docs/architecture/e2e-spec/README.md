# TradeXV2 End-to-End Architectural Specification

**Status:** Draft v1.0 — documentation-first, pre-implementation  
**Reference:** [NautilusTrader](file:///Users/apple/Downloads/nautilus_trader-develop) `docs/concepts/` + `nautilus_trader/system/kernel.py`  
**Audience:** Principal engineers, runtime owners, broker adapter authors  
**Rule:** No implementation of the redesign until this suite is accepted. Local patches that hide systemic gaps are forbidden.

This suite specifies **what TradeXV2 must become** for real-money NSE/IST trading, using NautilusTrader as the reference for:

- common kernel across backtest / sandbox / live
- single-threaded deterministic event core
- MessageBus + Cache as the system spine
- Strategy → RiskEngine → ExecutionEngine → ExecutionClient flow
- fail-fast / crash-only recovery
- research-to-live parity with **no strategy code changes**

TradeXV2 keeps its own layering (`domain → application → infrastructure → runtime`) and Indian-market plugins. It does **not** become a Nautilus fork; it adopts Nautilus’s *runtime contracts*.

---

## Document map

| # | Document | Covers |
|---|---|---|
| 00 | [Nautilus reference mapping](00-nautilus-reference.md) | What we take from Nautilus, what we deliberately discard, component↔component map |
| 01 | [System intent & invariants](01-system-intent-and-invariants.md) | Product contract, trust boundaries, enforceable invariants I1–I10 |
| 02 | [Kernel & components](02-kernel-and-components.md) | TradeXKernel, MessageBus, Cache, DataEngine, ExecutionEngine, RiskEngine, Portfolio |
| 03 | [Domain model](03-domain-model.md) | Value objects, entities, aggregates, FSMs, bounded contexts |
| 04 | [Messaging & events](04-messaging-and-events.md) | Message kinds, topic hierarchy, EventType catalog, immutability rules |
| 05 | [Data flow](05-data-flow.md) | Life of a quote / bar / option chain (Nautilus-aligned sequence) |
| 06 | [Execution flow](06-execution-flow.md) | Life of an order: place / fill / cancel / modify (live + replay) |
| 07 | [Risk & safety](07-risk-and-safety.md) | Pre-trade gates, TradingState, kill-switch, throttling, fail-closed |
| 08 | [Time, parity & environments](08-time-parity-and-environments.md) | Clock, environments (backtest/sandbox/live), Zero-Parity contract |
| 09 | [Reconciliation & cache](09-reconciliation-and-cache.md) | Cache as SoT, reconcile-on-refresh, drift severity |
| 10 | [Ports & contracts](10-ports-and-contracts.md) | Protocol signatures, Expected Behavior Contracts |
| 11 | [As-built gaps & migration](11-asbuilt-gaps-and-migration.md) | Current violations vs this spec, ordered migration, acceptance tests |
| 12 | [Market data storage review](12-market-data-storage-review.md) | Why root `market_data/` exists; lake vs state vs `src/market_data` package; target `data/lake` + `data/state` |

**Related (prior work):**
- [Principal Engineer Review](../../superpowers/reviews/PRINCIPAL-ENGINEER-REVIEW-TradeXV2-vs-nautilus.md)
- [Earlier architectural sketch](../../superpowers/reviews/ARCHITECTURAL-SPECIFICATION-TradeXV2.md) — superseded by this suite
- [Target layering](../target-layering.md) · [Roadmap](../roadmap.md) · [Backlog G1–G8](../backlog.md)

---

## How to read

1. Start with **00** (Nautilus mapping) — establishes vocabulary.
2. Read **01–02** for the system shape.
3. Read **05–06** for the two critical E2E paths (data + execution).
4. Read **08** before accepting any research-to-live claim.
5. Use **11** as the implementation gate: no code until acceptance criteria are listed and owned.

---

## Non-goals of this suite

- Rewriting TradeXV2 in Rust / Cython.
- Multi-process / multi-node cluster design (one kernel per process, like Nautilus).
- Speculative brokers or exchanges beyond the plugin model.
- Mocking real-money paths for “unit” convenience.
