"""Async resource lifecycle manager.

Tracks named resources with async cleanup functions. Thread-safe and
async-context-manager aware.

Usage:
    from infrastructure.async_resource_manager import AsyncResourceManager

    arm = AsyncResourceManager()
    arm.register("db_pool", pool, pool.async_close_all)

    async with arm.acquire("db_pool") as pool:
        conn = await pool.acquire()

    # On shutdown:
    await arm.shutdown_all()
"""

from __future__ import annotations

import asyncio
import logging
import threading
from collections.abc import Awaitable, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any

from infrastructure.health import HealthResult, HealthStatus, HealthRegistry

logger = logging.getLogger(__name__)


@dataclass
class _AsyncResourceEntry:
    """Internal record for a registered async resource."""
    resource: Any
    cleanup_fn: Callable[[], Any] | Callable[[], Awaitable[Any]] | None
    acquired: bool = False


class AsyncResourceManager:
    """Manages named resources with async cleanup support.

    Resources are cleaned up in reverse registration order on shutdown.
    Uses threading.Lock for sync methods and asyncio.Lock for async methods.

    Parameters
    ----------
    health_registry:
        Optional HealthRegistry to integrate with. If provided,
        a health check is registered that reports resource status.
    """

    def __init__(self, health_registry: HealthRegistry | None = None) -> None:
        self._sync_lock = threading.Lock()
        self._async_lock = asyncio.Lock()
        self._resources: dict[str, _AsyncResourceEntry] = {}
        self._shutdown_called = False
        self._health_registry = health_registry

        if health_registry is not None:
            health_registry.register("async_resources", self._health_check)

    def register(
        self,
        name: str,
        resource: Any,
        cleanup_fn: Callable[[], Any] | Callable[[], Awaitable[Any]] | None = None,
    ) -> None:
        """Register a resource with an optional cleanup function.

        Parameters
        ----------
        name:
            Unique name for the resource.
        resource:
            The resource object to track.
        cleanup_fn:
            Callable (sync or async) to clean up the resource.

        Raises
        ------
        ValueError
            If a resource with this name is already registered.
        """
        with self._sync_lock:
            if name in self._resources:
                raise ValueError(f"Resource '{name}' is already registered")
            self._resources[name] = _AsyncResourceEntry(
                resource=resource,
                cleanup_fn=cleanup_fn,
            )
            logger.debug("AsyncResourceManager: registered '%s'", name)

    def unregister(self, name: str) -> None:
        """Remove a resource without cleaning it up."""
        with self._sync_lock:
            self._resources.pop(name, None)
            logger.debug("AsyncResourceManager: unregistered '%s'", name)

    def get(self, name: str) -> Any | None:
        """Get a registered resource by name. Returns None if not found."""
        with self._sync_lock:
            entry = self._resources.get(name)
            return entry.resource if entry is not None else None

    @asynccontextmanager
    async def acquire(self, name: str):
        """Async context manager that yields a resource.

        Parameters
        ----------
        name:
            Name of the resource to acquire.

        Yields
        ------
        The registered resource.

        Raises
        ------
        KeyError
            If no resource is registered with this name.
        """
        async with self._async_lock:
            entry = self._resources.get(name)
            if entry is None:
                raise KeyError(f"Resource '{name}' not registered")
            entry.acquired = True

        try:
            yield entry.resource
        finally:
            async with self._async_lock:
                entry = self._resources.get(name)
                if entry is not None:
                    entry.acquired = False

    async def shutdown_all(self) -> None:
        """Clean up all registered resources in reverse registration order.

        Supports both sync and async cleanup functions. Errors during
        cleanup are logged but do not prevent subsequent resources
        from being cleaned up.
        """
        if self._shutdown_called:
            logger.debug("AsyncResourceManager.shutdown_all: already called")
            return

        async with self._async_lock:
            self._shutdown_called = True
            names = list(reversed(list(self._resources.keys())))

        logger.info(
            "AsyncResourceManager: shutting down %d resources in reverse order",
            len(names),
        )

        errors = []
        for name in names:
            async with self._async_lock:
                entry = self._resources.pop(name, None)

            if entry is None:
                continue

            try:
                if entry.cleanup_fn is not None:
                    result = entry.cleanup_fn()
                    if asyncio.iscoroutine(result):
                        await result
                logger.debug("AsyncResourceManager: cleaned up '%s'", name)
            except Exception as exc:
                logger.warning(
                    "AsyncResourceManager: cleanup failed for '%s': %s: %s",
                    name,
                    type(exc).__name__,
                    exc,
                )
                errors.append((name, exc))

        if errors:
            logger.warning(
                "AsyncResourceManager: %d cleanup errors occurred", len(errors)
            )

    def _health_check(self) -> HealthResult:
        """Health check callback for the HealthRegistry."""
        if self._shutdown_called:
            return HealthResult(
                status=HealthStatus.DEGRADED,
                message="AsyncResourceManager has been shut down",
            )

        with self._sync_lock:
            count = len(self._resources)
            names = list(self._resources.keys())

        if count == 0:
            return HealthResult(
                status=HealthStatus.HEALTHY,
                message="No resources registered",
            )

        return HealthResult(
            status=HealthStatus.HEALTHY,
            message=f"{count} resource(s) registered",
            details={"resources": names, "count": count},
        )
