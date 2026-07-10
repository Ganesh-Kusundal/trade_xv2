"""StrategyRegistry - Plugin discovery and registration for strategies.

Enables dynamic strategy loading without modifying existing code.
Supports both manual registration and importlib-based discovery.

Usage:
    # Manual registration
    StrategyRegistry.register("momentum", MomentumStrategy)

    # Auto-discovery from package
    StrategyRegistry.discover("analytics.strategy.builtins")

    # Get strategy by name
    strategy = StrategyRegistry.get("momentum")

    # List all strategies
    names = StrategyRegistry.list()  # ["momentum", "breakout", "halftrend"]
"""

from __future__ import annotations

import importlib
import logging
from typing import ClassVar

from analytics.strategy.protocols import Strategy

logger = logging.getLogger(__name__)


class StrategyRegistry:
    """Central registry for strategy discovery and instantiation.

    This class provides a plugin architecture for strategies, enabling:
    - Manual registration of strategy classes
    - Auto-discovery from Python packages via importlib
    - Factory-style instantiation by name
    - Listing of all available strategies

    The registry is a singleton pattern implemented via class methods,
    ensuring a single source of truth for strategy discovery across
    the entire application.
    """

    _registry: ClassVar[dict[str, type[Strategy]]] = {}

    @classmethod
    def register(cls, name: str, strategy_class: type[Strategy]) -> None:
        """Register a strategy class with a canonical name.

        Args:
            name: Canonical strategy name (e.g., "momentum", "breakout")
            strategy_class: Strategy class implementing Strategy protocol
        """
        if name in cls._registry:
            logger.warning("Strategy '%s' already registered, overwriting", name)
        cls._registry[name] = strategy_class
        logger.info("Strategy registered: %s -> %s", name, strategy_class.__name__)

    @classmethod
    def get(cls, name: str) -> type[Strategy]:
        """Get a strategy class by name.

        Args:
            name: Strategy name

        Returns:
            Strategy class

        Raises:
            KeyError: If strategy not found
        """
        if name not in cls._registry:
            raise KeyError(
                f"Strategy '{name}' not found. Available: {', '.join(cls._registry.keys())}"
            )
        return cls._registry[name]

    @classmethod
    def create(cls, name: str, **kwargs) -> Strategy:
        """Create a strategy instance by name.

        Args:
            name: Strategy name
            **kwargs: Arguments to pass to strategy constructor

        Returns:
            Strategy instance
        """
        strategy_class = cls.get(name)
        return strategy_class(**kwargs)

    @classmethod
    def list(cls) -> list[str]:
        """List all registered strategy names.

        Returns:
            Sorted list of strategy names available in the registry
        """
        return sorted(cls._registry.keys())

    @classmethod
    def discover(cls, package_path: str) -> int:
        """Auto-discover strategies in a package.

        Scans the package for modules and imports them. Strategies
        register themselves via module-level calls to StrategyRegistry.register().

        Args:
            package_path: Python package path (e.g., "analytics.strategy.builtins")

        Returns:
            Number of strategies discovered
        """
        before_count = len(cls._registry)

        try:
            package = importlib.import_module(package_path)
            if hasattr(package, "__path__"):
                import pkgutil

                for _importer, modname, _ispkg in pkgutil.iter_modules(package.__path__):
                    full_name = f"{package_path}.{modname}"
                    try:
                        importlib.import_module(full_name)
                        logger.debug("Discovered strategy module: %s", full_name)
                    except Exception as exc:
                        logger.warning("Failed to import strategy module %s: %s", full_name, exc)
        except Exception as exc:
            logger.error("Failed to discover strategies in %s: %s", package_path, exc)

        discovered = len(cls._registry) - before_count
        logger.info("Discovered %d strategies in %s", discovered, package_path)
        return discovered

    @classmethod
    def clear(cls) -> None:
        """Clear all registered strategies (useful for testing)."""
        cls._registry.clear()
