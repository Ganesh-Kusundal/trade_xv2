"""Runtime composition root — plugin discovery and wiring."""

from runtime.discovery import discover_brokers
from runtime.execution_target import resolve_clock, resolve_fill_source
from runtime.factory import RuntimeFactory
from runtime.runtime import Runtime
from runtime.startup import boot

__all__ = [
    "Runtime",
    "RuntimeFactory",
    "boot",
    "discover_brokers",
    "resolve_clock",
    "resolve_fill_source",
]
