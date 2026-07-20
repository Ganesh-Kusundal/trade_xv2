# Concurrency Model

## Overview

TradeXV2 uses a hybrid concurrency model combining:

1. **Asyncio event loop** - Process-wide runtime loop for I/O-bound operations
2. **ThreadPoolExecutor** - For CPU-bound or blocking operations
3. **Daemon threads** - For long-running background services

## Event Loop Architecture

### Process-Wide Runtime Loop

The platform uses a single, centralized event loop managed by `src/runtime/event_loop.py`:

```python
_RUNTIME_LOOP: asyncio.AbstractEventLoop | None = None
_LOOP_LOCK = threading.Lock()
_RUNTIME_LOOP_THREAD: threading.Thread | None = None
```

**Key functions:**
- `ensure_runtime_loop()` - Creates the loop once (process-wide singleton)
- `ensure_runtime_loop_running()` - Starts the loop in a daemon thread
- `run_coro_sync()` - Runs async code from sync contexts (safe bridge)
- `new_dedicated_loop()` - Creates isolated loops for specific subsystems

**Thread safety:** The loop singleton is protected by `_LOOP_LOCK` (threading.Lock).

### Daemon Thread Pattern

The runtime loop runs in a daemon thread:
```python
thread = threading.Thread(
    target=loop.run_forever, name="runtime-event-loop", daemon=True
)
```

**Shutdown:** Daemon threads are killed when the main thread exits. The loop itself has no explicit shutdown signal - it relies on daemon thread semantics.

## Threading Usage

### ThreadPoolExecutor Locations

| Module | Purpose | Workers |
|--------|---------|---------|
| `infrastructure/batch_executor.py` | Parallel broker/datalake operations | Configurable |
| `analytics/scanner/runner.py` | Concurrent scanner execution | Configurable |
| `datalake/gateway.py` | Parallel DuckDB reads | Configurable |
| `brokers/dhan/wire.py` | Parallel order operations | 5 |
| `interface/ui/commands/doctor/` | Parallel health checks | Configurable |
| `application/services/download_engine.py` | Parallel symbol downloads | Configurable |

### Daemon Threads

| Module | Thread Name | Purpose |
|--------|-------------|---------|
| `runtime/event_loop.py` | `runtime-event-loop` | Main asyncio loop |
| `application/oms/reconciliation_service.py` | `reconciliation-timer` | OMS reconciliation |
| `application/oms/daily_pnl_reset_scheduler.py` | - | Daily PnL reset |
| `application/oms/lifecycle.py` | `dlq-monitor` | Dead letter queue monitor |
| `infrastructure/lifecycle/lifecycle.py` | - | Application lifecycle |
| `infrastructure/event_bus/` | - | Event bus processing |

## Async/Sync Boundaries

### Async → Sync Bridge

`run_coro_sync()` in `src/runtime/event_loop.py` handles the async→sync transition:

1. If called from within a running loop → uses `run_coroutine_threadsafe()`
2. If runtime loop exists and is running → uses `run_coroutine_threadsafe()`
3. If runtime loop exists but not running → uses `run_until_complete()`
4. If no runtime loop → creates ephemeral loop (short-lived)

**Thread safety:** Uses `_LOOP_LOCK` when accessing `_RUNTIME_LOOP`.

### Sync → Async Bridge

`src/application/streaming/orchestrator.py` bridges broker WebSocket threads to asyncio:

```python
def on_raw_frame(frame: Any) -> None:
    loop = asyncio.get_event_loop()
    loop.call_soon_threadsafe(
        asyncio.ensure_future,
        self._tick_router.handle_frame(session_id, frame, stream_kind),
    )
```

**Pattern:** Broker threads call `loop.call_soon_threadsafe()` to schedule async work on the runtime loop.

## Shared State Protection

### Threading Locks (RLock/Lock)

| Module | Lock Type | Protected State |
|--------|-----------|-----------------|
| `application/oms/order_manager.py` | RLock | Order state |
| `application/oms/position_manager.py` | RLock | Position state |
| `application/oms/risk_manager.py` | RLock | Risk config, daily PnL |
| `application/oms/idempotency_guard.py` | Lock | Idempotency cache |
| `application/oms/reconciliation_service.py` | Event | Stop/request signals |
| `application/scheduling/quota_scheduler.py` | Lock | Quota state |
| `application/composer/registry.py` | RLock | Broker registry |
| `application/audit.py` | Lock | Audit log writes |

### Asyncio Locks

| Module | Lock | Protected State |
|--------|------|-----------------|
| `application/streaming/orchestrator.py` | asyncio.Lock | Sessions, subscriptions |
| `application/streaming/session_manager.py` | asyncio.Lock | Session lifecycle |
| `application/streaming/reconnect_controller.py` | asyncio.Lock | Reconnect state |
| `application/streaming/tick_router.py` | asyncio.Lock | Tick routing |
| `infrastructure/cache_redis.py` | asyncio.Lock | Redis cache |

### Broker-Specific Locks

| Module | Lock Type | Purpose |
|--------|-----------|---------|
| `brokers/upstox/websocket/v3_decoder.py` | Lock | Decode failure counter |
| `brokers/upstox/websocket/market_data_v3.py` | RLock, Lock | Listeners, sends |
| `brokers/upstox/auth/holders.py` | RLock | Token holder state |
| `brokers/upstox/auth/token_manager.py` | RLock, Lock, Event | Token refresh |

## Context Variables

`src/domain/ports/session_context.py` uses `ContextVar` for ambient session context:

**Thread safety note:** ContextVars do not auto-propagate to ThreadPoolExecutor workers unless `contextvars.copy_context().run(...)` is used.

## Known Risks

### 1. Daemon Thread Shutdown

**Risk:** Daemon threads are killed abruptly on process exit without cleanup.

**Impact:** 
- WebSocket connections may not close gracefully
- In-flight orders may be lost
- State may be corrupted

**Mitigation:** Application lifecycle management in `infrastructure/lifecycle/lifecycle.py` attempts graceful shutdown before exit.

### 2. Ephemeral Event Loops

**Risk:** `run_coro_sync()` creates ephemeral loops when no runtime loop exists.

**Impact:** Background tasks scheduled on ephemeral loops are killed when the loop closes.

**Mitigation:** Documentation warns against this pattern; `ensure_runtime_loop_running()` should be called early.

### 3. ContextVar Propagation

**Risk:** ContextVars don't propagate to ThreadPoolExecutor workers.

**Impact:** Ambient session context may be missing in worker threads.

**Mitigation:** Use Universe-stamped instruments in worker threads; avoid relying on ContextVars in thread pools.

### 4. Mixed Locking Strategies

**Risk:** Some modules use threading locks, others use asyncio locks.

**Impact:** Potential deadlocks if async code tries to acquire a threading lock, or vice versa.

**Mitigation:** Clear separation: threading locks for sync code, asyncio locks for async code. The `run_coro_sync()` bridge handles the transition safely.

### 5. No Explicit Loop Shutdown

**Risk:** The runtime event loop has no explicit shutdown mechanism.

**Impact:** Long-running tasks may not complete gracefully.

**Mitigation:** Daemon thread semantics ensure cleanup on process exit; application lifecycle handles graceful shutdown.

## Thread Safety Patterns

### Safe Patterns

1. **Single event loop ownership** - One daemon thread owns the runtime loop
2. **Lock-protected singletons** - Module-level state protected by locks
3. **Thread-safe bridges** - `run_coro_sync()` and `call_soon_threadsafe()` handle async/sync transitions
4. **Immutable data** - Many domain objects are frozen dataclasses

### Unsafe Patterns to Avoid

1. **Direct asyncio access from threads** - Always use `run_coro_sync()` or `call_soon_threadsafe()`
2. **Shared mutable state without locks** - All shared state must be lock-protected
3. **ContextVar reliance in thread pools** - Use explicit parameters instead
4. **Long-running sync code in async context** - Use ThreadPoolExecutor for blocking operations

## Recommendations

1. **Standardize shutdown** - Add explicit shutdown signals for daemon threads
2. **Document thread ownership** - Clearly mark which thread owns which resources
3. **Audit lock ordering** - Prevent deadlocks by establishing consistent lock acquisition order
4. **Consider structured concurrency** - Evaluate asyncio.TaskGroup for better task lifecycle management
5. **Add thread safety tests** - Verify concurrent access patterns in unit tests