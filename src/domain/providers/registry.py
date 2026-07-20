"""Provider Registry — central lookup for data and execution providers.

The registry is created at composition root and injected into all
aggregates and services.  It is the KEY architectural component
that replaces direct broker references throughout the system.

Thread-safety: Registration is expected during startup (single-threaded).
Lookup is lock-free (dict read).
"""

from __future__ import annotations

import threading
from typing import Any


class ProviderRegistry:
    """Central registry for all data and execution providers.

    Usage::

        registry = ProviderRegistry()
        registry.register_data_provider("broker", BrokerDataProvider(gateway))
        registry.register_data_provider("csv", CsvDataProvider("data/"))
        registry.register_execution_provider("broker", BrokerExecutionProvider(gateway))

        provider = registry.get_data_provider()  # returns "broker" (default)
        csv = registry.get_data_provider("csv")   # explicit lookup
    """

    def __init__(self) -> None:
        self._data_providers: dict[str, Any] = {}
        self._execution_providers: dict[str, Any] = {}
        self._default_data: str = ""
        self._default_execution: str = ""
        self._lock = threading.Lock()

    # ── Registration ────────────────────────────────────────────────

    def register_data_provider(self, name: str, provider: Any) -> None:
        """Register a data provider.  Call during startup."""
        with self._lock:
            self._data_providers[name] = provider
            if not self._default_data:
                self._default_data = name

    def register_execution_provider(self, name: str, provider: Any) -> None:
        """Register an execution provider.  Call during startup."""
        with self._lock:
            self._execution_providers[name] = provider
            if not self._default_execution:
                self._default_execution = name

    def set_default_data_provider(self, name: str) -> None:
        """Override the default data provider."""
        if name not in self._data_providers:
            available = list(self._data_providers.keys())
            raise KeyError(f"Data provider '{name}' not registered. Available: {available}")
        self._default_data = name

    def set_default_execution_provider(self, name: str) -> None:
        """Override the default execution provider."""
        if name not in self._execution_providers:
            available = list(self._execution_providers.keys())
            raise KeyError(f"Execution provider '{name}' not registered. Available: {available}")
        self._default_execution = name

    # ── Lookup ──────────────────────────────────────────────────────

    def get_data_provider(self, name: str | None = None) -> Any:
        """Get a data provider by name, or the default.

        Raises
        ------
        KeyError
            If the named provider is not registered.
        """
        key = name or self._default_data
        if key not in self._data_providers:
            available = list(self._data_providers.keys())
            raise KeyError(f"Data provider '{key}' not registered. Available: {available}")
        return self._data_providers[key]

    def get_execution_provider(self, name: str | None = None) -> Any:
        """Get an execution provider by name, or the default.

        Raises
        ------
        KeyError
            If the named provider is not registered.
        """
        key = name or self._default_execution
        if key not in self._execution_providers:
            available = list(self._execution_providers.keys())
            raise KeyError(f"Execution provider '{key}' not registered. Available: {available}")
        return self._execution_providers[key]

    # ── Introspection ───────────────────────────────────────────────

    def list_data_providers(self) -> list[str]:
        """List all registered data provider names."""
        return list(self._data_providers.keys())

    def list_execution_providers(self) -> list[str]:
        """List all registered execution provider names."""
        return list(self._execution_providers.keys())

    @property
    def has_data_providers(self) -> bool:
        """True when at least one data provider is registered."""
        return len(self._data_providers) > 0

    @property
    def has_execution_providers(self) -> bool:
        """True when at least one execution provider is registered."""
        return len(self._execution_providers) > 0

    def __repr__(self) -> str:
        return (
            f"ProviderRegistry("
            f"data={self.list_data_providers()}, "
            f"exec={self.list_execution_providers()})"
        )
