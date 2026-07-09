"""Broker registry — unified broker-agnostic factory for creating gateways.

Phase 4: single point of truth for broker gateway creation.  All env file
paths and factory dispatch logic live here so neither ``BrokerService``
nor ``cli/main.py`` duplicate them.

Usage::

    from cli.services.broker_registry import create_gateway, list_available_brokers

    # With auto-detected env path
    gw = create_gateway("dhan")

    # With explicit env path
    gw = create_gateway("upstox", env_path=Path("/path/to/.env.upstox"))

    # List registered brokers
    brokers = list_available_brokers()
    # -> [{"name": "dhan", "env_file": ".env.local", "available": True}, ...]
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# ── Default env file paths (convention over configuration) ──────────────────
# Each broker looks for its env file relative to the project root.
# ``None`` means the broker has no env file (e.g. paper, datalake).
ENV_FILES: dict[str, str | None] = {
    "dhan": ".env.local",
    "upstox": ".env.upstox",
    "paper": None,
    # Phase 6: read-only gateway backed by the local Parquet datalake.
    # No env file is needed (no broker credentials).
    "datalake": None,
}


def resolve_env_path(broker: str, env_path: str | Path | None = None) -> Path | None:
    """Resolve the environment file path for *broker*.

    If *env_path* is provided it is returned as-is.  Otherwise the
    default convention from :const:`ENV_FILES` is used.  Returns
    ``None`` when the broker has no env file (e.g. ``paper``).
    """
    if env_path is not None:
        return Path(env_path)
    default = ENV_FILES.get(broker)
    if default is not None:
        return Path(default)
    return None


def create_gateway(
    broker: str = "dhan",
    env_path: str | Path | None = None,
    load_instruments: bool = True,
    event_bus: Any | None = None,
    lifecycle: Any | None = None,
    risk_manager: Any | None = None,
) -> Any | None:
    """Create a gateway for the specified broker.

    Parameters
    ----------
    broker : str
        Broker name: ``"dhan"``, ``"upstox"``, or ``"paper"``.
    env_path : str or Path or None
        Path to the broker's environment file.  If ``None`` the
        conventional default (``.env.local`` for Dhan, ``.env.upstox``
        for Upstox) is used.
    load_instruments : bool
        Whether to load instrument master data on creation.
    event_bus : Any or None
        Optional :class:`~brokers.common.event_bus.EventBus`.
    lifecycle : Any or None
        Optional :class:`~brokers.common.lifecycle.LifecycleManager`.
    risk_manager : Any or None
        Optional :class:`~brokers.common.oms.risk_manager.RiskManager`.

    Returns
    -------
    :class:`~brokers.common.gateway.MarketDataGateway` or ``None`` on failure.
    """
    broker = broker.lower().strip()

    # Pass the env_path directly — builders handle None internally
    # by falling back to their default env file convention.
    builders = {
        "dhan": _create_dhan,
        "upstox": _create_upstox,
        "paper": _create_paper,
        # Phase 6: read-only datalake gateway (parquet-backed).
        "datalake": _create_datalake,
    }
    builder = builders.get(broker)
    if builder is None:
        logger.error("Unknown broker: %s (expected one of %s)", broker, list(builders))
        return None

    return builder(
        env_path,
        load_instruments=load_instruments,
        event_bus=event_bus,
        lifecycle=lifecycle,
        risk_manager=risk_manager,
    )


def bootstrap_gateway(*args: Any, **kwargs: Any) -> Any | None:
    """Deprecated alias for :func:`create_gateway`.

    Retained so legacy call sites (``brokers/common/bootstrap.py``,
    ``cli/services/broker_facade.py``, doctor strategies) keep working
    after the registry refactor renamed the factory to
    :func:`create_gateway`. New code should call ``create_gateway``
    directly.
    """
    return create_gateway(*args, **kwargs)


def list_available_brokers() -> list[dict[str, Any]]:
    """Return a list of registered brokers with their status.

    Each entry: ``{"name": ..., "env_file": ..., "available": bool}``.
    """
    result: list[dict[str, Any]] = []
    for name, env_file in ENV_FILES.items():
        available = True
        if env_file is not None:
            available = Path(env_file).exists()
        result.append({
            "name": name,
            "env_file": env_file,
            "available": available,
        })
    return result


# ── Broker-specific builders ────────────────────────────────────────────────


def _create_dhan(
    env_path: str | Path | None,
    *,
    load_instruments: bool = True,
    event_bus: Any | None = None,
    lifecycle: Any | None = None,
    risk_manager: Any | None = None,
) -> Any | None:
    """Create a Dhan gateway via :class:`BrokerFactory`."""
    try:
        from brokers.dhan.factory import BrokerFactory

        resolved = Path(env_path) if env_path is not None else None
        return BrokerFactory().create(
            env_path=resolved,
            load_instruments=load_instruments,
            event_bus=event_bus,
            lifecycle=lifecycle,
            risk_manager=risk_manager,
        )
    except ImportError:
        logger.warning("Dhan broker not installed")
        return None
    except Exception as exc:
        logger.error("Failed to create Dhan gateway: %s", exc)
        return None


def _create_upstox(
    env_path: str | Path | None,
    *,
    load_instruments: bool = True,
    event_bus: Any | None = None,
    lifecycle: Any | None = None,
    risk_manager: Any | None = None,
) -> Any | None:
    """Create an Upstox gateway via :class:`UpstoxBrokerFactory`."""
    try:
        from brokers.upstox.factory import UpstoxBrokerFactory

        resolved = Path(env_path) if env_path is not None else None
        return UpstoxBrokerFactory().create(
            env_path=resolved,
            load_instruments=load_instruments,
            event_bus=event_bus,
            lifecycle=lifecycle,
            risk_manager=risk_manager,
        )
    except ImportError:
        logger.warning("Upstox broker not installed")
        return None
    except Exception as exc:
        logger.error("Failed to create Upstox gateway: %s", exc)
        return None


def _create_paper(
    env_path: Path | None = None,  # noqa: ARG001
    **kwargs: Any,  # noqa: ARG001
) -> Any | None:
    """Create a Paper gateway (no broker connection needed)."""
    try:
        from brokers.paper import PaperGateway

        return PaperGateway()
    except ImportError:
        logger.warning("Paper gateway not available")
        return None


def _create_datalake(
    env_path: Path | None = None,  # noqa: ARG001
    *,
    root: str = "market_data",
    **kwargs: Any,  # noqa: ARG001
) -> Any | None:
    """Create a read-only DataLake gateway (parquet-backed).

    Phase 6: this is the same gateway used by the analytics
    ``BacktestEngine`` and ``ReplayEngine`` so the diagnostic CLI
    can run against historical data without a live broker. Trading
    methods (``place_order``, ``cancel_order``, etc.) raise
    ``NotImplementedError`` — the datalake is read-only.
    """
    try:
        from datalake.gateway import DataLakeGateway

        return DataLakeGateway(root=root)
    except ImportError:
        logger.warning("DataLake gateway not available")
        return None
    except Exception as exc:
        logger.error("Failed to create DataLake gateway: %s", exc)
        return None


# ── Concrete-class accessors ───────────────────────────────────────────────
# ``broker_service`` (and any other cli module) must NOT import broker
# implementations directly — that breaks the ``CLI broker-implementation
# isolation`` contract.  broker_registry is the *sole* cli module permitted
# to know about concrete brokers, so it exposes the classes/factories here.


def get_paper_gateway_class() -> type:
    """Return the :class:`PaperGateway` class (no direct cli→brokers.paper import)."""
    from brokers.paper import PaperGateway

    return PaperGateway


def get_mock_broker_class() -> type:
    """Return the :class:`MockBroker` class (no direct cli→brokers.paper import)."""
    from brokers.paper.mock_broker import MockBroker

    return MockBroker


def create_seeded_mock_broker(name: str = "dhan") -> Any:
    """Delegate to ``brokers.paper.mock_broker.create_seeded_mock_broker``."""
    from brokers.paper.mock_broker import create_seeded_mock_broker as _create

    return _create(name)


def get_dhan_websocket_classes() -> tuple[type, type]:
    """Return ``(DhanMarketFeed, DhanOrderStream)`` without cli→brokers.dhan."""
    from brokers.dhan.websocket import DhanMarketFeed, DhanOrderStream

    return DhanMarketFeed, DhanOrderStream


def get_dhan_reconciliation_service_factory():
    """Return ``create_reconciliation_service`` without cli→brokers.dhan."""
    from brokers.dhan.reconciliation import create_reconciliation_service

    return create_reconciliation_service
