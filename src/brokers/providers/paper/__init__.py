"""Paper exchange plugin — domain-port simulator for OMS / live paths.

Ownership
---------
* **This package** — ``PaperGateway`` and execution/data providers that implement
  broker ports for paper trading and integration tests.
* **``analytics.paper``** — offline research backtest engine over DataFrames.
  Transaction costs live in :mod:`domain.trading_costs` for both.

Usage::

    from brokers.providers.paper import PaperGateway
    from domain.orders.requests import OrderRequest
    from domain.enums import Side

    gw = PaperGateway()
    q = gw.quote("RELIANCE", "NSE")
    o = gw.place_order(OrderRequest(symbol="RELIANCE", exchange="NSE", transaction_type=Side.BUY, quantity=10))
    b = gw.funds()
"""

from brokers.providers.paper.data_provider import PaperDataProvider
from brokers.providers.paper.execution_provider import PaperExecutionProvider
from brokers.providers.paper.paper_gateway import PaperGateway
from brokers.providers.paper.paper_market_data import PaperMarketData
from brokers.providers.paper.paper_orders import PaperOrders
from brokers.providers.paper.paper_portfolio import PaperPortfolio

# Self-register data + execution adapters (ADR-007)
from infrastructure.adapter_factory import (
    register_data_adapter,
    register_execution_provider,
)
from infrastructure.broker_plugin import BrokerPlugin, register_broker_plugin

register_data_adapter("paper", PaperDataProvider)
register_execution_provider("paper", PaperExecutionProvider)
register_broker_plugin(
    BrokerPlugin(
        broker_id="paper",
        env_file=None,
        default_mode="sim",
        supported_modes=frozenset({"sim", "market", "trade"}),
        is_live=False,
    )
)

from brokers.providers.paper.segment_mapper import PaperSegmentMapper
from domain.market.segment_registry import register_segment_mapper

register_segment_mapper("paper", PaperSegmentMapper)

__all__ = [
    "PaperExecutionProvider",
    "PaperGateway",
    "PaperMarketData",
    "PaperOrders",
    "PaperPortfolio",
]
