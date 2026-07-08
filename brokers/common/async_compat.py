"""Shared async/sync boundary helpers.

Re-exports from ``infrastructure.io.async_compat`` for backward compatibility.
New code should import from ``infrastructure.io.async_compat`` directly.
"""

from infrastructure.io.async_compat import connect_async_then, run_async_compat

__all__ = ["connect_async_then", "run_async_compat"]
