"""API service bootstrap — shared runtime wiring for the HTTP surface.

Composition root for datalake + trading runtime used by ``scripts/run_api_server``
and API tests. ``build_for_api`` lives in :mod:`runtime.api_compose` (not UI).
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Callable

from runtime.factory import Runtime

logger = logging.getLogger(__name__)


def initialize_api_services(
    project_root: Path | None = None,
    *,
    wire_orchestrator: bool = True,
    skip_parity_gate: bool = False,
    broker_service_factory: Callable[..., Any] | None = None,
) -> dict[str, Any]:
    """Build datalake services and unified trading runtime for the API."""
    root = project_root or Path(__file__).resolve().parent.parent.parent.parent

    from analytics.views.manager import ViewManager
    from datalake.storage.catalog import DataCatalog
    from datalake.gateway import DataLakeGateway
    from runtime.api_compose import build_for_api, register_broker_service_factory

    if broker_service_factory is not None:
        register_broker_service_factory(broker_service_factory)

    logger.info("Initializing TradeXV2 API services from interface API bootstrap...")

    # Canonical lake + catalog (data/lake), not legacy market_data/ (empty of parquet).
    from domain.ports.data_catalog import DEFAULT_CATALOG_PATH, DEFAULT_DATA_ROOT

    lake_root = root / DEFAULT_DATA_ROOT
    catalog_path = root / DEFAULT_CATALOG_PATH
    datalake_gateway = DataLakeGateway(root=str(lake_root))
    data_catalog = DataCatalog(root=str(lake_root), read_only=True)
    view_manager = ViewManager(
        catalog_path=catalog_path,
        read_only=True,
    )

    runtime: Runtime = build_for_api(
        wire_orchestrator=wire_orchestrator,
        skip_parity_gate=skip_parity_gate,
        broker_service_factory=broker_service_factory,
    )

    trading_context = runtime.trading_context
    event_bus = runtime.event_bus
    if trading_context is not None and event_bus is not trading_context.event_bus:
        logger.warning(
            "Runtime event_bus differs from TradingContext event_bus; using context bus"
        )
        event_bus = trading_context.event_bus

    # Create composers from broker infrastructure (if available)
    market_data_composer = None
    execution_composer = None
    broker_infra = runtime.broker_infrastructure
    if broker_infra is not None:
        from application.composer.factory import create_composers_from_infra

        risk_manager = trading_context.risk_manager if trading_context else None
        market_data_composer, execution_composer = create_composers_from_infra(
            infra=broker_infra,
            risk_manager=risk_manager,
        )
        logger.info("Composers created with risk_manager=%s", "yes" if risk_manager else "no")

    return {
        "datalake_gateway": datalake_gateway,
        "data_catalog": data_catalog,
        "view_manager": view_manager,
        "event_bus": event_bus,
        "trading_context": trading_context,
        "broker_service": runtime.broker_service,
        "market_data_composer": market_data_composer,
        "execution_composer": execution_composer,
        "runtime": runtime,
    }


__all__ = ["initialize_api_services"]
