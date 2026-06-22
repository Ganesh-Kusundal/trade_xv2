"""E2E test fixtures — shared utilities for end-to-end trading flow tests.

Provides:
- TradingContext factories with paper/mock brokers
- Synthetic market data generators
- Mock broker gateways
- Event capture utilities
- Time freezing helpers
"""

from tests.e2e.fixtures.data_generators import (
    generate_ohlcv_data,
    generate_multi_symbol_data,
    generate_trending_data,
    generate_mean_reverting_data,
)
from tests.e2e.fixtures.mock_brokers import (
    MockBrokerGateway,
    MockFailingBroker,
    MockLatencyBroker,
)
from tests.e2e.fixtures.trading_context_factory import (
    create_test_trading_context,
    create_paper_trading_context,
)
from tests.e2e.fixtures.event_capturer import EventCapturer

__all__ = [
    "generate_ohlcv_data",
    "generate_multi_symbol_data",
    "generate_trending_data",
    "generate_mean_reverting_data",
    "MockBrokerGateway",
    "MockFailingBroker",
    "MockLatencyBroker",
    "create_test_trading_context",
    "create_paper_trading_context",
    "EventCapturer",
]
