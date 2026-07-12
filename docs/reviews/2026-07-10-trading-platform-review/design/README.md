# TradeXV2 Target Design

This design package implements the design phase of the production-readiness plan. It defines ownership, contracts, state transitions, migration boundaries, and the P0 backlog before production-code refactoring begins.

## Documents

- [Expected execution contract](execution-contract.md)
- [State and flow specification](state-and-flow.md)
- [Bounded contexts and ownership](bounded-contexts-and-ownership.md)
- [Architecture decisions](adr-set.md)
- [Current-to-target migration matrix](migration-matrix.md)
- [P0 implementation backlog](p0-backlog.md)

## Non-negotiable target

Live, paper, replay, and backtest share one decision → risk → intent → submission outcome → fill → portfolio projection flow. Only the market-event source and fill model vary.

No external failure may be represented as valid empty data, zero capital, neutral features, successful cancellation, or a confirmed order. Ambiguous state is durable, visible, and blocks new entries until reconciled.
