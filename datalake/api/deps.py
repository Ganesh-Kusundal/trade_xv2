"""Dependency injection for API routers.

Provides FastAPI dependencies for:
- DataLakeGateway (historical data)
- ViewManager (DuckDB analytics views)
- DataCatalog (symbol metadata)
- EventBus (real-time events)
- BrokerService (live broker connections)
"""

from __future__ import annotations

import logging
from typing import Any, Callable

from fastapi import Depends, HTTPException, status

logger = logging.getLogger(__name__)

# Global service instances (populated during app startup)
_service_registry: dict[str, Any] = {}


def register_service(name: str, instance: Any) -> None:
    """Register a service instance in the global registry.
    
    Parameters
    ----------
    name:
        Service identifier (e.g., "datalake_gateway", "view_manager").
    instance:
        The service instance to register.
    """
    _service_registry[name] = instance
    logger.info("Service registered: %s", name)


def get_service(name: str, required: bool = True) -> Any:
    """Get a service instance by name.
    
    Parameters
    ----------
    name:
        Service identifier.
    required:
        If True, raises HTTPException when service is missing.
    
    Returns
    -------
    The service instance, or None if not found and required=False.
    """
    instance = _service_registry.get(name)
    if instance is None and required:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Service '{name}' not initialized",
        )
    return instance


# ── FastAPI Dependencies ─────────────────────────────────────────────────────

def get_datalake_gateway() -> Any:
    """Get DataLakeGateway instance for historical data queries."""
    return get_service("datalake_gateway")


def get_view_manager() -> Any:
    """Get ViewManager instance for DuckDB analytics queries."""
    return get_service("view_manager")


def get_data_catalog() -> Any:
    """Get DataCatalog instance for symbol metadata."""
    return get_service("data_catalog")


def get_event_bus() -> Any:
    """Get EventBus instance for real-time events."""
    return get_service("event_bus", required=False)


def get_broker_service() -> Any:
    """Get BrokerService instance for live broker connections."""
    return get_service("broker_service", required=False)


# ── Initialization Helper ────────────────────────────────────────────────────

def initialize_all_services(
    datalake_gateway: Any = None,
    view_manager: Any = None,
    data_catalog: Any = None,
    event_bus: Any = None,
    broker_service: Any = None,
    **additional_services: Any,
) -> None:
    """Initialize all services at once.
    
    Called during FastAPI app startup to wire up existing TradeXV2 services.
    
    Parameters
    ----------
    datalake_gateway:
        DataLakeGateway instance for historical OHLCV data.
    view_manager:
        ViewManager instance for DuckDB analytics views.
    data_catalog:
        DataCatalog instance for symbol metadata.
    event_bus:
        EventBus instance for real-time event publishing.
    broker_service:
        BrokerService instance for live broker connections.
    **additional_services:
        Additional services to register (key=name, value=instance).
    """
    if datalake_gateway is not None:
        register_service("datalake_gateway", datalake_gateway)
    if view_manager is not None:
        register_service("view_manager", view_manager)
    if data_catalog is not None:
        register_service("data_catalog", data_catalog)
    if event_bus is not None:
        register_service("event_bus", event_bus)
    if broker_service is not None:
        register_service("broker_service", broker_service)
    
    for name, instance in additional_services.items():
        register_service(name, instance)
    
    logger.info(
        "All services initialized: %s",
        list(_service_registry.keys()),
    )
