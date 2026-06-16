"""Regression tests for gateway issues found in the in-depth review.

Validates:
- Local imports hoisted (no `from brokers.dhan.segments import` inside methods)
- Hardcoded `"NSE_EQ"` replaced with `DEFAULT_SEGMENT` constant
- Upstox `option_chain` / `future_chain` / `get_trade_book` raise NotImplementedError
- `MarketDataGateway` contract is honored by both brokers
"""

from __future__ import annotations

import ast
import inspect
from pathlib import Path

import pytest

from brokers.common.gateway import MarketDataGateway


GATEWAY_DIR = Path(__file__).resolve().parents[2]


class TestGatewayImportHygiene:
    """No local imports of internal modules inside gateway methods."""

    def test_dhan_gateway_no_local_segment_imports(self):
        """EXCHANGE_TO_SEGMENT must be imported at module level in dhan/gateway.py."""
        import ast

        with open(GATEWAY_DIR / "dhan" / "gateway.py") as f:
            tree = ast.parse(f.read())

        # Top-level imports
        top_imports = set()
        for node in tree.body:
            if isinstance(node, ast.ImportFrom):
                for alias in node.names:
                    top_imports.add(alias.asname or alias.name)
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    top_imports.add(alias.asname or alias.name)

        assert "EXCHANGE_TO_SEGMENT" in top_imports, (
            "EXCHANGE_TO_SEGMENT must be imported at module level"
        )

        # No local imports of segments module inside functions
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module and "segments" in node.module:
                if node not in tree.body:  # not at top level
                    pytest.fail(
                        f"Local import of {node.module} found inside function"
                    )

    def test_dhan_gateway_no_local_websocket_imports(self):
        """DhanMarketFeed must be imported at module level in dhan/gateway.py."""
        with open(GATEWAY_DIR / "dhan" / "gateway.py") as f:
            tree = ast.parse(f.read())

        top_imports = set()
        for node in tree.body:
            if isinstance(node, ast.ImportFrom):
                for alias in node.names:
                    top_imports.add(alias.asname or alias.name)
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    top_imports.add(alias.asname or alias.name)

        assert "DhanMarketFeed" in top_imports, (
            "DhanMarketFeed must be imported at module level"
        )


class TestGatewaySegmentConstants:
    """Hardcoded segment strings replaced with constants."""

    def test_no_hardcoded_nse_eq_as_default_in_gateway(self):
        """No hardcoded 'NSE_EQ' used as a fallback default in gateway methods.

        Allowed: exchange string membership checks (e.g. `if exchange in ('NSE', 'NSE_EQ', ...)`).
        Forbidden: using as fallback in `EXCHANGE_TO_SEGMENT.get(..., 'NSE_EQ')`.
        """
        with open(GATEWAY_DIR / "dhan" / "gateway.py") as f:
            content = f.read()
        import re
        # Find all "NSE_EQ" used as a fallback default
        fallback_pattern = re.compile(r"\.get\([^,]+,\s*['\"]NSE_EQ['\"]\)")
        fallbacks = fallback_pattern.findall(content)
        assert len(fallbacks) == 0, (
            f"Found {len(fallbacks)} hardcoded 'NSE_EQ' fallback defaults, expected 0. "
            f"Use DEFAULT_SEGMENT constant instead."
        )

    def test_default_segment_constant_exists(self):
        from brokers.dhan.segments import DEFAULT_SEGMENT
        assert DEFAULT_SEGMENT == "NSE_EQ"


class TestUpstoxNotImplementedErrors:
    """Upstox unsupported endpoints must raise NotImplementedError, not return error dicts."""

    @pytest.fixture
    def upstox_gateway(self):
        from unittest.mock import MagicMock
        from brokers.upstox.gateway import UpstoxBrokerGateway
        gw = UpstoxBrokerGateway.__new__(UpstoxBrokerGateway)
        gw._broker = MagicMock()
        return gw

    def test_upstox_option_chain_raises(self, upstox_gateway):
        with pytest.raises(NotImplementedError, match="option chain"):
            upstox_gateway.option_chain("NIFTY", exchange="NFO")

    def test_upstox_future_chain_raises(self, upstox_gateway):
        with pytest.raises(NotImplementedError, match="future chain"):
            upstox_gateway.future_chain("NIFTY", exchange="NFO")

    def test_upstox_get_trade_book_raises(self, upstox_gateway):
        with pytest.raises(NotImplementedError, match="trade book"):
            upstox_gateway.get_trade_book()


class TestMarketDataGatewayContract:
    """Both brokers must implement every abstract method of MarketDataGateway."""

    @pytest.fixture
    def abstract_methods(self):
        return set(MarketDataGateway.__abstractmethods__)

    def test_dhan_gateway_implements_all_abstract(self, abstract_methods):
        from brokers.dhan.gateway import BrokerGateway as DhanGateway
        dhan_methods = set(dir(DhanGateway))
        missing = abstract_methods - dhan_methods
        assert not missing, f"Dhan gateway missing abstract methods: {missing}"

    def test_upstox_gateway_implements_all_abstract(self, abstract_methods):
        from brokers.upstox.gateway import UpstoxBrokerGateway
        upstox_methods = set(dir(UpstoxBrokerGateway))
        missing = abstract_methods - upstox_methods
        assert not missing, f"Upstox gateway missing abstract methods: {missing}"


class TestDhanGatewaySegmentMapping:
    """Dhan gateway uses EXCHANGE_TO_SEGMENT for all segment lookups."""

    @pytest.fixture
    def dhan_gateway(self):
        from unittest.mock import MagicMock
        from brokers.dhan.gateway import BrokerGateway as DhanGateway
        from brokers.dhan.resolver import SymbolResolver
        resolver = SymbolResolver()
        from brokers.dhan.domain import Instrument, Exchange, InstrumentType
        resolver._by_security_id = {"2885": Instrument(
            symbol="RELIANCE", exchange=Exchange.NSE, security_id="2885",
            instrument_type=InstrumentType.EQUITY,
        )}
        conn = MagicMock()
        conn.instruments = resolver
        conn._client.client_id = "test"
        conn._client.access_token = "test"
        gw = DhanGateway.__new__(DhanGateway)
        gw._conn = conn
        return gw

    def test_default_segment_used_when_exchange_not_mapped(self, dhan_gateway):
        """Fallback segment should use DEFAULT_SEGMENT constant, not hardcoded string."""
        from brokers.dhan.segments import DEFAULT_SEGMENT, EXCHANGE_TO_SEGMENT
        assert EXCHANGE_TO_SEGMENT.get("UNKNOWN", DEFAULT_SEGMENT) == "NSE_EQ"
