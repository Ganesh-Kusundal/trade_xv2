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
# ``None`` means the broker has no env file (e.g. paper).
ENV_FILES: dict[str, str | None] = {
    "dhan": ".env.local",
    "upstox": ".env.upstox",
    "paper": None,
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
