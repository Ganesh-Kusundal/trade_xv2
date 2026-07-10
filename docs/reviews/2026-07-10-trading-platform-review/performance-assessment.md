# Performance Assessment

## Verdict

The main risk is not a single slow function. It is unbounded work and shared mutable state on the live event path. The current design can work at low throughput but has no demonstrated capacity envelope for multiple strategies, symbols, brokers, or bursty market data.

## Real-time bottlenecks

- EventBus dispatch is synchronous; broker, OMS, persistence, and UI handlers can block feed processing (`src/infrastructure/event_bus/event_bus.py:455-468`).
- Feature fetching can block candidate processing and creates a one-thread executor per timeout call (`src/application/trading/trading_orchestrator.py:264-276`).
- Replay uses synchronous history access and `DataFrame.iterrows()` inside an async task (`src/interface/api/ws/replay.py:142-169`).
- Dhan and Upstox maintain multiple stream/reconnect layers, increasing duplicate work and contention.
- MarketBridge forwards all events into a process-wide queue before filtering; one burst can starve other clients (`src/interface/api/ws/bridge.py:32-93`).
- Drop-oldest queues have no resync protocol, so consumers can silently lose state transitions (`src/interface/api/ws/bridge.py:44-55`, `src/interface/api/ws/market.py:147-153`).
- SQLite order storage is single-process/single-writer and is not a horizontal scaling substrate (`src/infrastructure/persistence/sqlite_order_store.py:1-8`).

## Data and memory risks

- TTL/deque dedupe state can expire before delayed broker events arrive.
- Unbounded or insufficiently bounded event queues can either grow memory or discard ticks without recovery.
- Session recording and Parquet caching are best-effort; performance pressure can produce incomplete audit/data artifacts.
- WebSocket `create_task` sends and suppressed listener errors make backpressure and delivery latency unobservable (`src/brokers/upstox/websocket/market_data_v3.py:259-285,347-360`).

## Required measurements

Instrument and budget:

- market event receive-to-validation latency;
- validation-to-signal latency;
- signal-to-risk decision latency;
- risk-to-broker submission latency;
- broker acknowledgement and fill latency;
- event queue depth, dropped sequence count, and projection lag;
- per-symbol and per-broker tick throughput;
- reconnect duration and stale-data duration;
- CPU, RSS, GC pauses, and persistence fsync latency.

Benchmarks must fail promotion when budgets are exceeded. Current CI benchmark handling is advisory (`.github/workflows/ci.yml:345-352`), so it cannot protect a latency-sensitive system.

## Scaling recommendation

Keep a single-writer execution ledger per account/strategy partition. Scale market-data normalization and analytics horizontally, but do not scale order mutation by simply adding API workers. Use partition ownership, durable queues, and idempotent consumers before moving beyond one process. Replace SQLite only when the ledger contract and partition model are explicit; changing databases first would preserve the state-race problem.
