"""Paper broker -- simulated trading for testing and development.

Mirrors the Dhan BrokerGateway interface so it can be used as a drop-in replacement.

Usage::

    from brokers.paper import PaperGateway

    gw = PaperGateway()
    q = gw.quote("RELIANCE", "NSE")
    o = gw.place_order("RELIANCE", "NSE", "BUY", 10)
    b = gw.funds()
"""

from brokers.paper.paper_gateway import PaperGateway
from brokers.paper.paper_market_data import PaperMarketData
from brokers.paper.paper_orders import PaperOrders
from brokers.paper.paper_portfolio import PaperPortfolio

__all__ = [
    "PaperGateway",
    "PaperMarketData",
    "PaperOrders",
    "PaperPortfolio",
]
