"""Upstox broker bundles — extracted client/adapter/order construction modules.

These bundles decompose the UpstoxBroker god-facade into focused, independently
testable components while preserving the existing public attribute surface.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from domain.constants import DEFAULT_EXCHANGE


@dataclass
class ClientBundle:
    """Raw HTTP clients grouped by domain area.

    Extracted from UpstoxBroker._build_raw_clients to enable independent testing
    and reduce constructor wall-of-code.
    """

    # Market data clients
    market_data_v2: Any
    market_data_v3: Any
    historical_v2: Any
    historical_v3: Any

    # Options / portfolio / margin clients
    options_client: Any
    portfolio_client: Any
    margin_client: Any
    market_status_client: Any
    futures_client: Any
    expired_instruments_client: Any

    # Order clients
    order_client: Any
    gtt_client: Any

    # Intelligence clients
    news_client: Any
    intelligence_client: Any
    kill_switch_client: Any
    static_ip_client: Any

    # Miscellaneous clients
    ipo_client: Any
    payments_client: Any
    mutual_funds_client: Any
    fundamentals_client: Any
    historical_service: Any


@dataclass
class AdapterBundle:
    """Domain adapters grouped by capability area.

    Extracted from UpstoxBroker._build_adapters to enable independent testing.
    """

    # Market data adapters
    market_data: Any
    options: Any
    portfolio: Any
    margin: Any
    market_status: Any
    futures: Any
    news: Any
    intelligence_snapshot: Any
    kill_switch: Any
    exit_all: Any


@dataclass
class OrderBundle:
    """Order-related objects for command and query paths.

    Extracted from UpstoxBroker._build_order_path to enable independent testing.
    """

    idempotency_cache: Any
    order_command: Any
    order_query: Any
    gtt: Any
    slice: Any
    cover: Any
    alert: Any
    feed_authorizer: Any
    market_data_websocket: Any
    portfolio_stream: Any


__all__ = [
    "AdapterBundle",
    "ClientBundle",
    "DEFAULT_EXCHANGE",
    "OrderBundle",
]