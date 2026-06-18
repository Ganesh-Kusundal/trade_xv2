# AsyncEventBus Migration Guide

## Overview

This guide describes the integration of `AsyncEventBus` into the Trade_XV2 live trading flow and provides a step-by-step migration path from synchronous to asynchronous event processing.

## Architecture

### Current State (Sync-Only)

```
┌─────────────┐
│  Publisher  │  (sync)
└──────┬──────┘
       │ publish(DomainEvent)
       ▼
┌─────────────┐
│  EventBus   │  (synchronous dispatch)
└──────┬──────┘
       │ handler(event)
       ▼
┌─────────────┐
│  Handlers   │  (blocking)
└─────────────┘
```

### Target State (Async with Backpressure)

```
┌─────────────┐
│  Publisher  │  (async)
└──────┬──────┘
       │ await publish(type, payload)
       ▼
┌─────────────┐
│ AsyncEventBus│  (bounded queue + backpressure)
│  [maxsize=N]│
└──────┬──────┘
       │ FIFO dispatch worker
       ▼
┌─────────────┐
│  Handlers   │  (sync→executor, async→direct)
└─────────────┘
```

## Implementation Files

### 1. AsyncEventBusFactory (`brokers/common/event_bus/factory.py`)

**Location**: `brokers/common/event_bus/factory.py`  
**Lines**: 1-329  
**Purpose**: Factory that creates sync or async EventBus based on configuration

**Key Classes**:
- `AsyncEventBusFactory`: Factory class with three creation methods
  - `create_from_config()`: Creates bus based on env vars or explicit flags
  - `create_async()`: Forces AsyncEventBus creation
  - `create_sync()`: Forces sync EventBus creation
- `AsyncPublishAdapter`: Wrapper providing uniform async publish API
- `async_publish_wrapper()`: Helper function to create adapter

**Configuration Priority**:
1. Explicit `force_async` or `force_sync` parameter (highest)
2. Environment variable `USE_ASYNC_EVENT_BUS` (1=true, 0=false)
3. Default: synchronous EventBus (backward compatible)

**Example Usage**:
```python
from brokers.common.event_bus import AsyncEventBusFactory

# Create based on config (defaults to sync)
bus, is_async = AsyncEventBusFactory.create_from_config()

# Force async
async_bus, _ = AsyncEventBusFactory.create_async(maxsize=2000)

# Force sync
sync_bus, _ = AsyncEventBusFactory.create_sync(metrics=my_metrics)
```

### 2. TradingContext Integration (`brokers/common/oms/context.py`)

**Modified Lines**:
- L12-20: Added imports for `AsyncEventBus`, `AsyncEventBusFactory`, `AsyncPublishAdapter`
- L88: Added `async_bus` parameter to `__init__`
- L106-119: Added async_bus initialization logic
- L234-288: Added async bus properties (`async_bus`, `is_async_bus`, `async_publisher`)
- L290-357: Added async lifecycle methods (`start_async_bus`, `stop_async_bus`, etc.)

**New Parameters**:
```python
TradingContext(
    # ... existing params ...
    async_bus: AsyncEventBus | None = None,  # NEW: AsyncEventBus instance
)
```

**New Properties**:
```python
ctx.async_bus          # AsyncEventBus | None
ctx.is_async_bus       # bool
ctx.async_publisher    # AsyncPublishAdapter | None
```

**New Methods**:
```python
await ctx.start_async_bus()
await ctx.stop_async_bus(timeout_seconds=10.0)
await ctx.wait_async_bus_completion(timeout_seconds=None)
stats = ctx.get_async_bus_stats()  # dict | None
```

### 3. CLI Integration Example (`cli/services/async_event_bus_integration.py`)

**Location**: `cli/services/async_event_bus_integration.py`  
**Lines**: 1-326  
**Purpose**: Helper functions and migration examples for CLI services

**Key Functions**:
- `create_async_bus_for_trading()`: Creates production-ready async bus
- `wire_async_bus_into_context()`: Wires async bus into TradingContext
- `initialize_async_trading_flow()`: Starts async bus and returns publisher
- `shutdown_async_trading_flow()`: Gracefully stops async bus

**Example Usage**:
```python
from cli.services.async_event_bus_integration import (
    create_async_bus_for_trading,
    wire_async_bus_into_context,
    initialize_async_trading_flow,
    shutdown_async_trading_flow,
)

# Setup
async_bus = create_async_bus_for_trading(maxsize=2000)
ctx = wire_async_bus_into_context(async_bus, metrics=my_metrics)

# Start
publisher = await initialize_async_trading_flow(ctx)

# Use
await publisher.publish("ORDER_PLACED", {"order_id": "123"})

# Shutdown
stats = await shutdown_async_trading_flow(ctx)
```

## Migration Phases

### Phase 1: Opt-In (Current) ✅

**Status**: Implemented and tested  
**Goal**: Enable async bus opt-in via explicit parameter  
**Risk**: Zero - existing code unaffected

**Actions**:
1. ✅ Created `AsyncEventBusFactory`
2. ✅ Added `async_bus` parameter to `TradingContext`
3. ✅ Created `AsyncPublishAdapter` for uniform API
4. ✅ Added lifecycle methods to `TradingContext`

**Testing**:
```bash
# Run existing tests (should pass unchanged)
pytest brokers/common/event_bus/tests/

# Test async integration
python -c "from brokers.common.oms.context import TradingContext; print('✓')"
```

### Phase 2: Environment Control (Next)

**Goal**: Enable async bus via environment variable  
**Timeline**: After Phase 1 validation in staging

**Actions**:
1. Set `USE_ASYNC_EVENT_BUS=1` in staging environment
2. Monitor queue depth, latency, and error rates
3. Validate backpressure behavior under load
4. Update CLI services to use `AsyncEventBusFactory.create_from_config()`

**Environment Variables**:
```bash
# Enable async bus
export USE_ASYNC_EVENT_BUS=1

# Configure backpressure policy
export ASYNC_BUS_BACKPRESSURE=BLOCK  # BLOCK, DROP, or ERROR

# Configure queue size (via factory parameter)
# Default: 1000, recommended for production: 2000-5000
```

**Integration Points**:
- `cli/services/broker_service.py`: Update `_ensure_initialized()` to use factory
- `cli/services/oms_setup.py`: Pass async_bus to TradingContext
- `brokers/paper/paper_gateway.py`: Add async_bus parameter

### Phase 3: Async Default (Future)

**Goal**: Make async bus the default after all publishers migrated  
**Timeline**: After Phase 2 production validation

**Actions**:
1. Migrate all `event_bus.publish()` calls to `async_publisher.publish()`
2. Make `AsyncEventBusFactory.create_from_config()` default to async
3. Update documentation and examples
4. Remove sync-only code paths (optional)

**Publisher Migration Checklist**:
- [ ] `brokers/dhan/websocket.py` (TICK, DEPTH, ORDER_UPDATED, TRADE)
- [ ] `brokers/upstox/websocket/portfolio_stream.py`
- [ ] `brokers/common/orchestrator/trading_orchestrator.py`
- [ ] `brokers/common/oms/order_manager.py`
- [ ] `brokers/common/oms/position_manager.py`
- [ ] `brokers/common/oms/reconciliation_service.py`
- [ ] `brokers/dhan/orders.py`
- [ ] `brokers/upstox/orders/order_command_adapter.py`
- [ ] `brokers/dhan/depth_20.py`
- [ ] `brokers/dhan/depth_200.py`

## Code Migration Examples

### Example 1: Simple Publisher Migration

**Before (Sync)**:
```python
from brokers.common.event_bus import DomainEvent

def place_order(self, order_data: dict) -> None:
    event = DomainEvent.now(
        "ORDER_PLACED",
        payload=order_data,
        symbol=order_data.get("symbol"),
        source="OrderService",
    )
    self._event_bus.publish(event)
```

**After (Async-Compatible)**:
```python
async def place_order(self, order_data: dict) -> None:
    # Use async publisher if available
    if self._context.async_publisher:
        await self._context.async_publisher.publish(
            "ORDER_PLACED",
            payload=order_data,
            symbol=order_data.get("symbol"),
            source="OrderService",
        )
    else:
        # Fallback to sync (backward compatible)
        event = DomainEvent.now(
            "ORDER_PLACED",
            payload=order_data,
            symbol=order_data.get("symbol"),
            source="OrderService",
        )
        self._event_bus.publish(event)
```

### Example 2: Gateway Integration

**Before**:
```python
class DhanGateway(MarketDataGateway):
    def __init__(self, event_bus: EventBus | None = None):
        self._event_bus = event_bus or EventBus()
```

**After**:
```python
from brokers.common.event_bus import (
    AsyncEventBusFactory,
    EventBus,
)
from brokers.common.event_bus.async_event_bus import AsyncEventBus

class DhanGateway(MarketDataGateway):
    def __init__(
        self,
        event_bus: EventBus | None = None,
        async_bus: AsyncEventBus | None = None,
    ):
        self._event_bus = event_bus or EventBus()
        self._async_bus = async_bus
        self._is_async = async_bus is not None
        
        # Create unified publisher
        if self._is_async:
            self._publisher = async_publish_wrapper(async_bus, is_async=True)
        else:
            self._publisher = async_publish_wrapper(self._event_bus, is_async=False)
    
    async def _publish_tick(self, quote: dict) -> None:
        await self._publisher.publish(
            "TICK",
            payload={"quote": quote},
            symbol=quote.symbol,
            source="DhanMarketFeed",
        )
```

### Example 3: Lifecycle Management

**Before**:
```python
def start_trading(self):
    ctx = TradingContext()
    # ... setup ...
    self.lifecycle.start_all()
```

**After**:
```python
async def start_trading(self):
    async_bus = create_async_bus_for_trading(maxsize=2000)
    ctx = TradingContext(async_bus=async_bus)
    
    # ... setup handlers ...
    
    # Start async bus
    await ctx.start_async_bus()
    
    # Start other services
    self.lifecycle.start_all()

async def stop_trading(self):
    # Stop async bus first (drain pending events)
    await self.ctx.stop_async_bus(timeout_seconds=10.0)
    
    # Stop other services
    self.lifecycle.stop_all()
```

## Testing Strategy

### Unit Tests

```python
import pytest
from brokers.common.event_bus import AsyncEventBusFactory
from brokers.common.oms.context import TradingContext

def test_sync_bus_creation():
    bus, is_async = AsyncEventBusFactory.create_from_config(force_sync=True)
    assert not is_async
    assert isinstance(bus, EventBus)

def test_async_bus_creation():
    bus, is_async = AsyncEventBusFactory.create_from_config(force_async=True)
    assert is_async
    from brokers.common.event_bus.async_event_bus import AsyncEventBus
    assert isinstance(bus, AsyncEventBus)

def test_trading_context_with_async_bus():
    async_bus, _ = AsyncEventBusFactory.create_from_config(force_async=True)
    ctx = TradingContext(async_bus=async_bus, replay_events=False)
    
    assert ctx.async_bus is not None
    assert ctx.is_async_bus is True
    assert ctx.async_publisher is not None

def test_trading_context_sync_only():
    ctx = TradingContext(replay_events=False)
    
    assert ctx.async_bus is None
    assert ctx.is_async_bus is False
    assert ctx.async_publisher is None
```

### Integration Tests

```python
import asyncio
import pytest
from cli.services.async_event_bus_integration import (
    create_async_bus_for_trading,
    wire_async_bus_into_context,
    initialize_async_trading_flow,
    shutdown_async_trading_flow,
)

@pytest.mark.asyncio
async def test_async_trading_flow():
    # Setup
    async_bus = create_async_bus_for_trading(maxsize=100)
    ctx = wire_async_bus_into_context(async_bus, replay_events=False)
    
    # Subscribe test handler
    received = []
    ctx.async_bus.subscribe("TEST", lambda e: received.append(e))
    
    # Initialize
    publisher = await initialize_async_trading_flow(ctx)
    
    # Publish
    await publisher.publish("TEST", {"data": "value"})
    
    # Wait for processing
    await asyncio.sleep(0.5)
    await ctx.wait_async_bus_completion(timeout=2.0)
    
    # Verify
    assert len(received) == 1
    
    # Shutdown
    stats = await shutdown_async_trading_flow(ctx)
    assert stats["event_count"] == 1
```

## Performance Considerations

### Queue Sizing

| Scenario | Recommended maxsize | Backpressure Policy |
|----------|---------------------|---------------------|
| Low-frequency trading (<100 events/sec) | 1000 | BLOCK |
| Medium-frequency (100-1000 events/sec) | 2000-5000 | BLOCK |
| High-frequency (>1000 events/sec) | 5000-10000 | DROP or ERROR |
| Market data replay | 10000+ | BLOCK |

### Backpressure Policies

- **BLOCK** (default): Publisher waits until queue has space
  - ✅ Guarantees no event loss
  - ❌ May block publisher indefinitely if consumer is slow
  - Use when: Event loss is unacceptable

- **DROP**: Publisher drops event if queue is full
  - ✅ Never blocks publisher
  - ❌ Events may be lost
  - Use when: Fresh data is more important than old data (e.g., tick updates)

- **ERROR**: Publisher raises exception if queue is full
  - ✅ Forces explicit error handling
  - ❌ Requires try/except at every publish site
  - Use when: You need to detect and handle backpressure explicitly

### Memory Usage

Each queued event consumes approximately:
- Event metadata: ~200 bytes
- Payload dictionary: ~500 bytes (varies by payload size)
- Total per event: ~700 bytes

Example: `maxsize=5000` → ~3.5 MB maximum queue memory

## Monitoring and Observability

### Metrics

The async bus publishes metrics via `EventMetrics`:
- `event_count`: Total events processed
- `error_count`: Handler failures
- `dropped_count`: Events dropped due to backpressure
- `queue_size`: Current queue depth
- `is_full`: Whether queue is at capacity

**Access via TradingContext**:
```python
stats = ctx.get_async_bus_stats()
print(f"Queue depth: {stats['queue_size']}/{stats['maxsize']}")
print(f"Events processed: {stats['event_count']}")
print(f"Errors: {stats['error_count']}")
print(f"Dropped: {stats['dropped_count']}")
```

### Alerting Thresholds

| Metric | Warning | Critical |
|--------|---------|----------|
| queue_size / maxsize | > 70% | > 90% |
| error_count / event_count | > 1% | > 5% |
| dropped_count | > 0 | > 10 |

### Logging

The async bus logs at these levels:
- **INFO**: Bus start/stop, configuration
- **DEBUG**: Event dispatch, handler invocation
- **WARNING**: Queue full (DROP policy), handler failures
- **ERROR**: Queue full (ERROR policy), worker errors

## Troubleshooting

### Issue: Async bus not starting

**Symptom**: `RuntimeError: AsyncEventBus not running, dropping event`

**Solution**:
```python
# Ensure you call start_async_bus() before publishing
await ctx.start_async_bus()

# Verify bus is running
assert ctx.async_bus.is_running
```

### Issue: Events not being processed

**Symptom**: Queue depth increasing, handlers not called

**Solution**:
```python
# Check if worker task is running
stats = ctx.get_async_bus_stats()
if stats['is_running'] is False:
    # Worker crashed, restart
    await ctx.start_async_bus()

# Check for handler errors
if stats['error_count'] > 0:
    logger.warning(f"{stats['error_count']} handler failures detected")
```

### Issue: Backpressure causing delays

**Symptom**: Publishers blocking, high latency

**Solution**:
1. Increase `maxsize` parameter
2. Change backpressure policy to DROP (if event loss is acceptable)
3. Optimize handler performance (reduce blocking I/O)
4. Scale out handler processing (multiple workers)

### Issue: Memory pressure

**Symptom**: High memory usage, OOM errors

**Solution**:
1. Reduce `maxsize` parameter
2. Use DROP or ERROR backpressure policy
3. Monitor queue depth and alert before reaching capacity
4. Profile handlers for memory leaks

## Rollback Plan

If async bus causes issues in production:

1. **Immediate**: Set `USE_ASYNC_EVENT_BUS=0` (or remove env var)
2. **Short-term**: Use `force_sync=True` in factory calls
3. **Long-term**: Revert to sync EventBus until issues resolved

The sync code paths remain fully functional and tested throughout the migration.

## References

- `AsyncEventBus` implementation: `brokers/common/event_bus/async_event_bus.py`
- `EventBus` (sync): `brokers/common/event_bus/event_bus.py`
- `TradingContext`: `brokers/common/oms/context.py`
- Factory: `brokers/common/event_bus/factory.py`
- Integration example: `cli/services/async_event_bus_integration.py`

## Changelog

- **2026-06-18**: Phase 1 implementation complete
  - Created `AsyncEventBusFactory`
  - Added `async_bus` parameter to `TradingContext`
  - Created `AsyncPublishAdapter` for uniform API
  - Added lifecycle methods to `TradingContext`
  - Created integration examples and migration guide

