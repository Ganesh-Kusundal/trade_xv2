# Executive Summary

## Verdict

**Do not enable unattended live trading with material capital.** The repository is a strong platform foundation, but its correctness contract is not yet enforced across live trading, paper trading, replay, and backtesting. The most dangerous defects are silent: stale or missing market data can look valid, broker failures can become empty results, retries can duplicate non-idempotent orders, and local order/position/PnL state can remain plausible while diverging from the broker.

The current working tree contains a sensible broker-kernel direction (`src/brokers/common/`) and meaningful conformance tests, but the target architecture is only partially adopted. Dhan still owns bespoke reconnect paths; Upstox and Dhan expose raw or broker-shaped data; Paper has a separate execution model; and the application contains multiple state representations for order, position, and PnL.

## What can go wrong silently?

1. Backtests default to `PURE_SIM`, which can skip OMS risk gates (`src/analytics/backtest/engine.py:47-119`); the API constructs this default in `src/interface/api/routers/backtest.py:98-105`.
2. Scanner candidates may lack correlation identity, causing repeated symbols to collide in OMS idempotency (`src/analytics/scanner/models.py:215-225`, `src/application/trading/trading_orchestrator.py:203-207,396-405`).
3. Feature failures are converted into skipped or neutral evaluation, while replay/paper can fall back to raw bars (`src/analytics/pipeline/pipeline.py:59-73`, `src/analytics/replay/engine.py:354-359`).
4. Datalake and broker reads commonly return empty/zero objects on failure (`src/datalake/gateway.py:154-180`, `src/brokers/dhan/data/data_provider.py:49-58`).
5. Reconciliation compares incomplete economic state: status/quantity rather than fills, average price, multiplier, realized PnL, and LTP (`src/domain/reconciliation_engine.py:81-165`).
6. Audit, session recording, and metrics are best-effort; an operationally green process can have an incomplete evidence trail.

## What breaks under real-time conditions?

- Synchronous event dispatch and feature fetching can put broker/OMS work on the market-data latency path (`src/infrastructure/event_bus/event_bus.py:455-468`, `src/application/trading/trading_orchestrator.py:264-276`).
- HTTP retry logic retries order writes after ambiguous timeouts, risking duplicate live orders (`src/brokers/dhan/api/http_client.py:425-453`, `src/brokers/upstox/auth/http.py:305-387`).
- WebSocket queues use drop-oldest behavior without a client resync protocol (`src/interface/api/ws/bridge.py:44-55`, `src/interface/api/ws/market.py:147-153`).
- One client's unsubscription can tear down a broker stream needed by another (`src/interface/api/ws/feed_wiring.py:84-95`).
- SQLite OMS storage assumes one process/one writer (`src/infrastructure/persistence/sqlite_order_store.py:1-8`); deployment does not visibly enforce this topology.

## Unsafe assumptions

- “Executed” means broker-confirmed execution; in dry-run it only means a signal passed local logic.
- “Same pipeline” means parity; timing, capital, fills, risk reservations, state ownership, and error semantics differ.
- “Empty” or zero-valued data means a legitimate market state.
- A connected socket or health check proves tradability; it does not prove fresh market data, valid margin, order-stream continuity, or safe order acceptance.
- The Paper broker is execution-parity; it uses synthetic data, instant fills, and a separate state model (`src/brokers/paper/paper_gateway.py:167-212`, `src/brokers/paper/paper_orders.py:243-361`).

## Top five systemic risks

1. **No single authoritative execution/PnL spine across modes.** Critical; blocks live trust and research validity.
2. **Ambiguous write retry/idempotency protocol.** Critical; duplicate orders are a direct money-loss risk.
3. **Lossy failure semantics at market-data, account, and broker boundaries.** Critical; stale/empty state can pass risk decisions.
4. **Incomplete reconciliation and duplicate/overfill protection.** Critical; local state can silently drift.
5. **Operational gates are non-truthful.** High; CI path mismatches, skipped live tests, non-blocking security/type gates, and advisory benchmarks can make green builds unsafe.

## Decision

Treat the current system as **research and controlled integration software**, not a production trading system. A production launch should be blocked until the action plan's P0 controls are demonstrated with real broker read-only/integration evidence and restart/recovery tests. The right redesign is contract-first and state-centric; a collection of patch-level guards will reproduce the current shotgun surgery.
