"""AsyncEventBusFactory — creates sync or async EventBus based on config.

This module provides a factory that determines whether to create a
synchronous EventBus or an asynchronous AsyncEventBus based on runtime
configuration. It enables gradual migration from sync to async event
processing without breaking existing code.

Migration Guide
---------------
Phase 1 (Current): Factory creates sync EventBus by default.
    - Existing code continues to work without changes
    - AsyncEventBus is available opt-in via config

Phase 2 (Opt-in): Set USE_ASYNC_EVENT_BUS=1 to enable async bus.
    - New async handlers can be registered
    - Existing sync handlers continue to work (run in executor)
    - Publishers must use async publish wrapper (see async_publish_wrapper)

Phase 3 (Default): Async becomes default after all publishers migrated.
    - Factory creates AsyncEventBus by default
    - Sync EventBus available via force_sync=True for legacy code

Usage
-----
    # Create bus based on config (defaults to sync)
    bus_or_async_bus, is_async = AsyncEventBusFactory.create_from_config()
    
    # Force async bus explicitly
    async_bus, _ = AsyncEventBusFactory.create_async()
    
    # Force sync bus explicitly
    sync_bus, _ = AsyncEventBusFactory.create_sync()
    
    # In async context with async bus:
    if is_async:
        await async_bus.publish("ORDER_PLACED", payload)
    else:
        sync_bus.publish(DomainEvent.now("ORDER_PLACED", payload))

Backward Compatibility
----------------------
The factory returns a tuple (bus, is_async) where:
- is_async=False: bus is an EventBus (sync)
- is_async=True: bus is an AsyncEventBus (async)

Callers should check is_async and use the appropriate publish API.
For gradual migration, use async_publish_wrapper() which handles
both cases transparently.
"""

from __future__ import annotations

import asyncio
import logging
import os
from typing import TYPE_CHECKING, Any

from infrastructure.event_bus.event_bus import DomainEvent, EventBus

if TYPE_CHECKING:
    from infrastructure.event_bus.async_event_bus import AsyncEventBus
    from infrastructure.event_bus.dead_letter_queue import DeadLetterQueue
    from brokers.common.observability.event_metrics import EventMetrics

logger = logging.getLogger(__name__)

# Config key for enabling async event bus
ASYNC_BUS_ENV_VAR = "USE_ASYNC_EVENT_BUS"


class AsyncEventBusFactory:
    """Factory that creates sync or async EventBus based on configuration.
    
    The factory inspects environment variables and optional config parameters
    to determine which bus type to instantiate. This enables gradual migration
    from synchronous to asynchronous event processing.
    
    Configuration Priority
    ----------------------
    1. Explicit force_async or force_sync parameter (highest priority)
    2. Environment variable USE_ASYNC_EVENT_BUS (1=true, 0=false)
    3. Default: synchronous EventBus (backward compatible)
    
    Examples
    --------
    >>> # Create based on environment (defaults to sync)
    >>> bus, is_async = AsyncEventBusFactory.create_from_config()
    
    >>> # Force async bus
    >>> async_bus, _ = AsyncEventBusFactory.create_async(maxsize=2000)
    
    >>> # Force sync bus (ignore env var)
    >>> sync_bus, _ = AsyncEventBusFactory.create_sync(metrics=my_metrics)
    """
    
    @classmethod
    def create_from_config(
        cls,
        *,
        force_async: bool = False,
        force_sync: bool = False,
        maxsize: int = 1000,
        event_log: Any | None = None,
        metrics: EventMetrics | None = None,
        dead_letter_queue: DeadLetterQueue | None = None,
    ) -> tuple[EventBus | AsyncEventBus, bool]:
        """Create EventBus based on configuration.
        
        Parameters
        ----------
        force_async:
            If True, always create AsyncEventBus (ignores env var).
        force_sync:
            If True, always create EventBus (ignores env var).
        maxsize:
            Queue size for async bus (ignored for sync bus).
        event_log:
            Optional event log for persistence.
        metrics:
            Optional metrics for observability.
        dead_letter_queue:
            Optional DLQ for failed handler invocations.
        
        Returns
        -------
        tuple[EventBus | AsyncEventBus, bool]:
            Tuple of (bus instance, is_async flag).
            If is_async is True, the bus is an AsyncEventBus.
            If is_async is False, the bus is a sync EventBus.
        
        Raises
        ------
        ValueError:
            If both force_async and force_sync are True.
        """
        if force_async and force_sync:
            raise ValueError("Cannot force both async and sync simultaneously")
        
        # Determine mode from parameters or environment
        if force_async:
            use_async = True
        elif force_sync:
            use_async = False
        else:
            # Check environment variable
            env_value = os.environ.get(ASYNC_BUS_ENV_VAR, "0")
            use_async = env_value in ("1", "true", "True", "TRUE")
        
        if use_async:
            logger.info(
                "Creating AsyncEventBus (maxsize=%d, source=%s)",
                maxsize,
                "force_async" if force_async else "env_var",
            )
            async_bus = cls.create_async(
                maxsize=maxsize,
                event_log=event_log,
                metrics=metrics,
                dead_letter_queue=dead_letter_queue,
            )
            return async_bus, True
        else:
            logger.info("Creating sync EventBus (source=default or force_sync)")
            sync_bus = cls.create_sync(
                event_log=event_log,
                metrics=metrics,
                dead_letter_queue=dead_letter_queue,
            )
            return sync_bus, False
    
    @classmethod
    def create_async(
        cls,
        *,
        maxsize: int = 1000,
        event_log: Any | None = None,
        metrics: EventMetrics | None = None,
        dead_letter_queue: DeadLetterQueue | None = None,
    ) -> AsyncEventBus:
        """Create an AsyncEventBus instance.
        
        Parameters
        ----------
        maxsize:
            Maximum queue size for backpressure (default 1000).
        event_log:
            Optional event log for persistence (not used by async bus).
        metrics:
            Optional metrics for observability.
        dead_letter_queue:
            Optional DLQ for failed handler invocations.
        
        Returns
        -------
        AsyncEventBus:
            Configured async event bus instance.
        """
        from infrastructure.event_bus.async_event_bus import (
            AsyncEventBus,
            BackpressurePolicy,
        )
        
        # Determine backpressure policy from environment
        policy_env = os.environ.get("ASYNC_BUS_BACKPRESSURE", "BLOCK")
        try:
            policy = BackpressurePolicy(policy_env)
        except ValueError:
            logger.warning(
                "Invalid backpressure policy '%s', defaulting to BLOCK",
                policy_env,
            )
            policy = BackpressurePolicy.BLOCK
        
        return AsyncEventBus(
            maxsize=maxsize,
            backpressure_policy=policy,
            event_log=event_log,
            metrics=metrics,
            dead_letter_queue=dead_letter_queue,
        )
    
    @classmethod
    def create_sync(
        cls,
        *,
        event_log: Any | None = None,
        metrics: EventMetrics | None = None,
        dead_letter_queue: DeadLetterQueue | None = None,
        logging_enabled: bool = True,
        fail_fast: bool = False,
    ) -> EventBus:
        """Create a synchronous EventBus instance.
        
        Parameters
        ----------
        event_log:
            Optional event log for persistence.
        metrics:
            Optional metrics for observability.
        dead_letter_queue:
            Optional DLQ for failed handler invocations.
        logging_enabled:
            If True, events are persisted to event_log before dispatch.
        fail_fast:
            If True, re-raises handler exceptions after capturing them.
        
        Returns
        -------
        EventBus:
            Configured synchronous event bus instance.
        """
        return EventBus(
            event_log=event_log,
            metrics=metrics,
            dead_letter_queue=dead_letter_queue,
            logging_enabled=logging_enabled,
            fail_fast=fail_fast,
        )


def async_publish_wrapper(
    event_bus: EventBus | AsyncEventBus,
    is_async: bool,
) -> AsyncPublishAdapter:
    """Create an async publish adapter that wraps sync or async bus.
    
    This is the primary migration tool for transitioning publishers from
    sync to async. The adapter provides a uniform async publish() method
    that works with both EventBus and AsyncEventBus.
    
    Migration Pattern
    -----------------
    Before (sync only):
        event_bus.publish(DomainEvent.now("ORDER_PLACED", payload))
    
    After (async-compatible):
        publisher = async_publish_wrapper(event_bus, is_async)
        await publisher.publish("ORDER_PLACED", payload)
    
    Parameters
    ----------
    event_bus:
        Either a sync EventBus or async AsyncEventBus instance.
    is_async:
        True if event_bus is an AsyncEventBus, False if sync EventBus.
    
    Returns
    -------
    AsyncPublishAdapter:
        Adapter with async publish() method.
    
    Examples
    --------
    >>> bus, is_async = AsyncEventBusFactory.create_from_config()
    >>> publisher = async_publish_wrapper(bus, is_async)
    >>> 
    >>> # In async function:
    >>> await publisher.publish("ORDER_PLACED", {"order_id": "123"})
    >>> await publisher.publish("TICK", {"ltp": 100.0}, symbol="RELIANCE")
    """
    return AsyncPublishAdapter(event_bus, is_async)


class AsyncPublishAdapter:
    """Adapter that provides async publish API for both sync and async buses.
    
    This adapter enables gradual migration by wrapping the publish call
    in an async interface regardless of the underlying bus type.
    
    For sync EventBus: publish runs in executor (asyncio.to_thread).
    For async AsyncEventBus: publish is awaited directly.
    
    Parameters
    ----------
    event_bus:
        Underlying event bus (sync or async).
    is_async:
        True if event_bus is AsyncEventBus.
    """
    
    def __init__(
        self,
        event_bus: EventBus | AsyncEventBus,
        is_async: bool,
    ) -> None:
        self._event_bus = event_bus
        self._is_async = is_async
    
    async def publish(
        self,
        event_type: str,
        payload: dict[str, Any],
        symbol: str | None = None,
        source: str | None = None,
        correlation_id: str | None = None,
    ) -> None:
        """Publish an event using async interface.
        
        Parameters
        ----------
        event_type:
            Type of the event.
        payload:
            Event payload dictionary.
        symbol:
            Optional symbol associated with the event.
        source:
            Optional source identifier.
        correlation_id:
            Optional correlation ID for tracing.
        """
        if self._is_async:
            # AsyncEventBus: use native async publish
            await self._event_bus.publish(
                event_type=event_type,
                payload=payload,
                symbol=symbol,
                source=source,
                correlation_id=correlation_id,
            )
        else:
            # Sync EventBus: wrap DomainEvent creation and publish in executor
            event = DomainEvent.now(
                event_type=event_type,
                payload=payload,
                symbol=symbol,
                source=source,
                correlation_id=correlation_id,
            )
            # Run sync publish in executor to avoid blocking event loop
            await asyncio.to_thread(self._event_bus.publish, event)
    
    @property
    def is_async(self) -> bool:
        """True if underlying bus is async."""
        return self._is_async
    
    @property
    def event_bus(self) -> EventBus | AsyncEventBus:
        """Underlying event bus instance."""
        return self._event_bus


def create_domain_event(**kwargs: Any) -> DomainEvent:
    """Build a domain event with current timestamp (composition-root helper)."""
    return DomainEvent.now(**kwargs)


__all__ = [
    "AsyncEventBusFactory",
    "AsyncPublishAdapter",
    "async_publish_wrapper",
    "ASYNC_BUS_ENV_VAR",
    "create_domain_event",
]
