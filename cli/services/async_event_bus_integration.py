"""AsyncEventBus integration example for CLI services.

This module demonstrates how to integrate AsyncEventBus into the
live trading flow. It provides helper functions and examples for:

1. Creating async bus via factory
2. Wiring async bus into TradingContext
3. Migrating existing sync publishers to async
4. Lifecycle management (start/stop)

Migration Status
----------------
- Phase 1 (Current): Opt-in async bus via explicit parameter
- Phase 2 (Future): Environment variable control (USE_ASYNC_EVENT_BUS=1)
- Phase 3 (Future): Async becomes default

Usage
-----
    from cli.services.async_event_bus_integration import (
        create_async_bus_for_trading,
        wire_async_bus_into_context,
    )
    
    # Create async bus
    async_bus = create_async_bus_for_trading()
    
    # Wire into TradingContext
    ctx = TradingContext(async_bus=async_bus)
    
    # Start async bus before trading
    await ctx.start_async_bus()
    
    # Use async publisher
    if ctx.async_publisher:
        await ctx.async_publisher.publish("ORDER_PLACED", payload)
    
    # Stop on shutdown
    await ctx.stop_async_bus()
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from infrastructure.event_bus import (
    AsyncEventBusFactory,
    AsyncPublishAdapter,
    async_publish_wrapper,
)
from infrastructure.event_bus.async_event_bus import AsyncEventBus
from infrastructure.event_bus.dead_letter_queue import DeadLetterQueue
from brokers.common.observability.event_metrics import EventMetrics

if TYPE_CHECKING:
    from brokers.common.oms.context import TradingContext

logger = logging.getLogger(__name__)


def create_async_bus_for_trading(
    *,
    maxsize: int = 2000,
    metrics: EventMetrics | None = None,
    dead_letter_queue: DeadLetterQueue | None = None,
    backpressure_policy: str = "BLOCK",
) -> AsyncEventBus:
    """Create an AsyncEventBus configured for live trading.
    
    This is the recommended way to create an async bus for the
    trading runtime. It sets sensible defaults for production use.
    
    Parameters
    ----------
    maxsize:
        Maximum queue size (default 2000). Larger queues provide
        more buffering but increase memory usage.
    metrics:
        EventMetrics instance for observability. If None, a new
        instance is created.
    dead_letter_queue:
        DLQ for failed handler invocations. If None, a new instance
        is created.
    backpressure_policy:
        Policy when queue is full: "BLOCK", "DROP", or "ERROR".
        Default "BLOCK" (publisher waits until space available).
    
    Returns
    -------
    AsyncEventBus:
        Configured async event bus ready for trading.
    
    Examples
    --------
    >>> async_bus = create_async_bus_for_trading(maxsize=5000)
    >>> async_bus.subscribe("ORDER_PLACED", my_handler)
    >>> await async_bus.start()
    """
    import os
    
    # Allow environment override for backpressure policy
    policy = os.environ.get("ASYNC_BUS_BACKPRESSURE", backpressure_policy)
    
    # Create metrics and DLQ if not provided
    effective_metrics = metrics or EventMetrics()
    effective_dlq = dead_letter_queue or DeadLetterQueue(max_size=5000)
    
    async_bus = AsyncEventBusFactory.create_async(
        maxsize=maxsize,
        metrics=effective_metrics,
        dead_letter_queue=effective_dlq,
    )
    
    logger.info(
        "Created AsyncEventBus for trading (maxsize=%d, policy=%s)",
        maxsize,
        policy,
    )
    
    return async_bus


def wire_async_bus_into_context(
    async_bus: AsyncEventBus,
    **context_kwargs: Any,
) -> TradingContext:
    """Create a TradingContext with async bus support.
    
    This helper wires the async bus into TradingContext and
    returns the fully configured context.
    
    Parameters
    ----------
    async_bus:
        AsyncEventBus instance to wire into the context.
    **context_kwargs:
        Additional arguments passed to TradingContext constructor.
    
    Returns
    -------
    TradingContext:
        Context with both sync and async bus support.
    
    Examples
    --------
    >>> async_bus = create_async_bus_for_trading()
    >>> ctx = wire_async_bus_into_context(
    ...     async_bus,
    ...     metrics=my_metrics,
    ...     dead_letter_queue=my_dlq,
    ... )
    """
    from brokers.common.oms.context import TradingContext
    
    ctx = TradingContext(
        async_bus=async_bus,
        **context_kwargs,
    )
    
    logger.info("TradingContext created with AsyncEventBus support")
    return ctx


async def initialize_async_trading_flow(
    ctx: TradingContext,
) -> AsyncPublishAdapter:
    """Initialize the async trading flow.
    
    This function:
    1. Starts the async bus dispatch worker
    2. Returns an async publisher for use in trading logic
    
    Call this during application startup after all handlers
    are subscribed but before publishing any events.
    
    Parameters
    ----------
    ctx:
        TradingContext with async_bus configured.
    
    Returns
    -------
    AsyncPublishAdapter:
        Adapter for publishing events via async API.
    
    Raises
    ------
    RuntimeError:
        If async_bus is not configured in the context.
    
    Examples
    --------
    >>> ctx = wire_async_bus_into_context(async_bus)
    >>> # ... subscribe handlers ...
    >>> publisher = await initialize_async_trading_flow(ctx)
    >>> await publisher.publish("ORDER_PLACED", {"order_id": "123"})
    """
    if not ctx.is_async_bus:
        raise RuntimeError(
            "TradingContext does not have AsyncEventBus configured. "
            "Pass async_bus parameter to TradingContext constructor."
        )
    
    # Start the async bus
    await ctx.start_async_bus()
    
    # Return the async publisher
    publisher = ctx.async_publisher
    if publisher is None:
        raise RuntimeError("Failed to create async publisher")
    
    logger.info("Async trading flow initialized")
    return publisher


async def shutdown_async_trading_flow(
    ctx: TradingContext,
    timeout_seconds: float = 10.0,
) -> dict[str, Any]:
    """Shutdown the async trading flow gracefully.
    
    This function:
    1. Waits for pending events to be processed
    2. Stops the async bus dispatch worker
    3. Returns statistics for logging
    
    Parameters
    ----------
    ctx:
        TradingContext with async_bus configured.
    timeout_seconds:
        Maximum time to wait for graceful shutdown (default 10s).
    
    Returns
    -------
    dict:
        Statistics including event count, error count, etc.
    
    Examples
    --------
    >>> stats = await shutdown_async_trading_flow(ctx)
    >>> print(f"Processed {stats['event_count']} events")
    """
    stats = ctx.get_async_bus_stats() or {}
    
    # Wait for pending events (with timeout)
    if ctx.is_async_bus:
        completed = await ctx.wait_async_bus_completion(
            timeout_seconds=timeout_seconds
        )
        if not completed:
            logger.warning(
                "Async bus did not complete within timeout (%.1fs)",
                timeout_seconds,
            )
        
        # Stop the async bus
        await ctx.stop_async_bus(timeout_seconds=timeout_seconds)
    
    logger.info(
        "Async trading flow shutdown: events=%d, errors=%d, dropped=%d",
        stats.get("event_count", 0),
        stats.get("error_count", 0),
        stats.get("dropped_count", 0),
    )
    
    return stats


# Example: Migrating a sync publisher to async
# ============================================================
#
# BEFORE (sync only):
# -------------------
# def place_order_sync(ctx: TradingContext, order_data: dict) -> None:
#     """Place order using sync EventBus."""
#     event = DomainEvent.now(
#         "ORDER_PLACED",
#         payload=order_data,
#         symbol=order_data.get("symbol"),
#         source="OrderService",
#     )
#     ctx.event_bus.publish(event)
#
#
# AFTER (async-compatible):
# -------------------------
# async def place_order_async(ctx: TradingContext, order_data: dict) -> None:
#     """Place order using async EventBus (or sync via adapter)."""
#     if ctx.async_publisher:
#         # Use async publisher (works with both sync and async bus)
#         await ctx.async_publisher.publish(
#             "ORDER_PLACED",
#             payload=order_data,
#             symbol=order_data.get("symbol"),
#             source="OrderService",
#         )
#     else:
#         # Fallback to sync publish (backward compatible)
#         event = DomainEvent.now(
#             "ORDER_PLACED",
#             payload=order_data,
#             symbol=order_data.get("symbol"),
#             source="OrderService",
#         )
#         ctx.event_bus.publish(event)
#
#
# MIGRATION CHECKLIST:
# --------------------
# 1. Add async_bus parameter to TradingContext constructor calls
# 2. Replace direct event_bus.publish() calls with async_publisher.publish()
# 3. Make calling functions async (def -> async def)
# 4. Add await to publisher calls
# 5. Add async bus start/stop to lifecycle management
# 6. Test with USE_ASYNC_EVENT_BUS=0 (sync) and =1 (async)
# 7. Monitor performance and queue depth in production
# 8. Once all publishers migrated, make async the default

