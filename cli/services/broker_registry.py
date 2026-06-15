"""Broker registry — broker-agnostic factory for creating gateways.

Usage:
    from cli.services.broker_registry import create_gateway
    gw = create_gateway("dhan")  # or "upstox", "paper"
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def create_gateway(
    broker: str = "dhan",
    env_path: str | Path | None = None,
    load_instruments: bool = True,
) -> Any | None:
    """Create a gateway for the specified broker.

    Parameters
    ----------
    broker : str
        Broker name: "dhan", "upstox", or "paper".
    env_path : str or Path or None
        Path to environment file (Dhan .env.local).
    load_instruments : bool
        Whether to load instrument master data.

    Returns
    -------
    MarketDataGateway instance, or None on failure.
    """
    broker = broker.lower().strip()

    if broker == "dhan":
        return _create_dhan(env_path, load_instruments)
    elif broker == "upstox":
        return _create_upstox(env_path, load_instruments)
    elif broker == "paper":
        return _create_paper()
    else:
        logger.error("Unknown broker: %s", broker)
        return None


def _create_dhan(env_path: str | Path | None, load_instruments: bool) -> Any | None:
    """Create Dhan gateway."""
    try:
        from brokers.dhan.factory import BrokerFactory
        return BrokerFactory.create(env_path=env_path, load_instruments=load_instruments)
    except ImportError:
        logger.warning("Dhan broker not installed")
        return None
    except Exception as e:
        logger.error("Failed to create Dhan gateway: %s", e)
        return None


def _create_upstox(env_path: str | Path | None, load_instruments: bool) -> Any | None:
    """Create Upstox gateway."""
    try:
        from brokers.upstox.factory import UpstoxBrokerFactory
        return UpstoxBrokerFactory.create(env_path=env_path, load_instruments=load_instruments)
    except ImportError:
        logger.warning("Upstox broker not installed")
        return None
    except Exception as e:
        logger.error("Failed to create Upstox gateway: %s", e)
        return None


def _create_paper() -> Any:
    """Create Paper gateway (no broker connection needed)."""
    try:
        from brokers.paper import PaperGateway
        return PaperGateway()
    except ImportError:
        logger.warning("Paper gateway not available")
        return None
