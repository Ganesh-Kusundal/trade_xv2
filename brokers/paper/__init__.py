"""Paper broker -- simulated trading for testing and development.

Mirrors the Dhan BrokerGateway interface so it can be used as a drop-in replacement.

Usage::

    from brokers.paper import PaperGateway

    gw = PaperGateway()
    q = gw.quote("RELIANCE", "NSE")
    o = gw.place_order("RELIANCE", "NSE", "BUY", 10)
    b = gw.funds()
"""

from brokers.paper.execution_provider import PaperExecutionProvider
from brokers.paper.paper_gateway import PaperGateway
from brokers.paper.paper_market_data import PaperMarketData
from brokers.paper.paper_orders import PaperOrders
from brokers.paper.paper_portfolio import PaperPortfolio

# Self-register execution adapter (ADR-007)
from infrastructure.adapter_factory import register_execution_provider
from infrastructure.broker_plugin import BrokerPlugin, register_broker_plugin

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

__all__ = [
    "PaperExecutionProvider",
    "PaperGateway",
    "PaperMarketData",
    "PaperOrders",
    "PaperPortfolio",
]
