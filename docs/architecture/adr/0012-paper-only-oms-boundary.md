# ADR-0012: Paper-Only OMS Boundary

## Status

Accepted — 2026-07-20

## Context

TradeXV2 is an analytics-first platform. Broker plugins (Dhan, Upstox) provide
**read-only market data**. Execution capability is selected at the composition
root via `ExecutionTargetKind`, not inferred from which broker is connected.

Prior wiring used `gateway ? live : paper`, which implied live execution whenever
a broker gateway existed. That contradicts the product scope and created shadow
state via `PaperGateway` portfolio/order APIs.

## Decision

1. **Product execution scope:** `ExecutionTargetKind.PAPER` only. Live execution
   remains a future plugin seam at `runtime/execution_target.py` — disabled until
   an explicit `tradex.execution` plugin replaces the target.

2. **Market-data broker × execution target matrix:**

   | Broker data plugin | Execution target | Valid? |
   |---|---|---|
   | Dhan / Upstox | PAPER | Yes — default operator path |
   | Dhan / Upstox | LIVE | No — disabled until live plugin |
   | PaperGateway | PAPER | Yes — test/synthetic market data only |
   | Any broker | BACKTEST / REPLAY | Yes — deterministic sim fills |

3. **OMS ownership:** OMS is the sole writer for paper orders, positions, capital
   ledger, idempotency, and audit state under `DataPaths.state_root`.
   `GatewayCapitalProvider.funds()` is **not** the paper risk capital source.

4. **Fill sources:**
   - `PaperFillSource` — PAPER (prices from market-data LTP/tick)
   - `SimulatedFillSource` — BACKTEST / REPLAY (deterministic)
   - `BrokerFillSource` — LIVE (future plugin only)

5. **PaperGateway role:** market-data / test adapter only. Must not be used as
   authoritative portfolio, order, or risk capital source in production paths.

6. **Ratchet:** only `src/runtime/execution_target.py` may branch on
   `ExecutionTargetKind` when wiring the kernel.

## Consequences

- Runtime defaults `TRADEX_EXECUTION_TARGET=paper`.
- `runtime/paper_session.py` composes TradingContext + OMS capital + PAPER target.
- Operator-facing PnL defaults to `ResearchMode.PARITY` (OMS-backed).
- `ResearchMode.PURE_SIM` remains explicit research-only output.
- Architecture tests enforce the boundary (see `test_paper_oms_boundary.py`).

## Deferred

Live broker fill stream, live order API surfaces, live reconciliation HA,
transactional outbox, and browser/API_KEY auth policy.
