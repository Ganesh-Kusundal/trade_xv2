"""E2E test fixtures — shared utilities for end-to-end trading flow tests.

Provides:
- TradingContext factories with paper/mock brokers
- Synthetic market data generators
- Mock broker gateways
- Event capture utilities
- Time freezing helpers
"""

from tests.e2e.fixtures.data_generators import (
    generate_mean_reverting_data,
    generate_multi_symbol_data,
    generate_ohlcv_data,
    generate_trending_data,
)
from tests.e2e.fixtures.event_capturer import EventCapturer
from tests.e2e.fixtures.mock_brokers import (
    MockBrokerGateway,
    MockFailingBroker,
    MockLatencyBroker,
)
from tests.e2e.fixtures.trading_context_factory import (
    create_paper_trading_context,
    create_test_trading_context,
)

__all__ = [
    "EventCapturer",
    "MockBrokerGateway",
    "MockFailingBroker",
    "MockLatencyBroker",
    "create_paper_trading_context",
    "create_test_trading_context",
    "generate_mean_reverting_data",
    "generate_multi_symbol_data",
    "generate_ohlcv_data",
    "generate_trending_data",
]
