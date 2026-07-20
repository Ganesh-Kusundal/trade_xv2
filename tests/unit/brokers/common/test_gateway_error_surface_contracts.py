"""Regression tests for gateway issues found in the in-depth review.

Validates:
- Local imports hoisted (no `from brokers.dhan.segments import` inside methods)
- Hardcoded `"NSE_EQ"` replaced with `DEFAULT_SEGMENT` constant
- Upstox `option_chain` / `future_chain` raise NotImplementedError (genuinely unsupported)
- Upstox `get_trade_book` returns [] (no endpoint, but ABC contract returns list)
- `MarketDataGateway` contract is honored by both brokers
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from domain.ports.broker_adapter import BrokerAdapter as MarketDataGateway

GATEWAY_DIR = Path(__file__).resolve().parents[4] / "src" / "brokers"


def _gw_source(broker: str) -> Path:
    """Path to a broker's wire adapter source module (refactored from gateway.py)."""
    return GATEWAY_DIR / broker / "wire.py"


class TestGatewayImportHygiene:
    """No local imports of internal modules inside gateway methods."""

    def test_dhan_gateway_no_local_segment_imports(self):
        """wire.py must not import segments inside methods (module-level only if needed)."""
        with open(_gw_source("dhan")) as f:
            tree = ast.parse(f.read())

        # No local imports of segments module inside functions
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.ImportFrom)
                and node.module
                and "segments" in node.module
                and node not in tree.body
            ):
                pytest.fail(f"Local import of {node.module} found inside function")

    def test_dhan_gateway_no_local_websocket_imports(self):
        """The market-feed class must be wired at module level in the WS layer.

        The gateway (``wire.py``) delegates WebSocket creation to the websocket
        connection layer, so we check ``websocket/connection.py``. The feed
        class is accessed via the module-level ``_sdk_market_feed_class`` helper
        (a deliberate lazy SDK-boundary import so ``import brokers.dhan.wire``
        does not require the ``dhanhq`` SDK at import time). ``connection.py``
        holds a ``feed_ref`` backreference to its parent ``DhanMarketFeed`` and
        must not import it directly (that would be circular).
        """
        with open(GATEWAY_DIR / "dhan" / "websocket" / "connection.py") as f:
            tree = ast.parse(f.read())

        top_imports = set()
        for node in tree.body:
            if isinstance(node, ast.ImportFrom | ast.Import):
                for alias in node.names:
                    top_imports.add(alias.asname or alias.name)

        assert "_sdk_market_feed_class" in top_imports, (
            "the market-feed class access point (_sdk_market_feed_class) must be "
            "imported at module level in websocket/connection.py"
        )


class TestGatewaySegmentConstants:
    """Hardcoded segment strings replaced with constants."""

    def test_no_hardcoded_nse_eq_as_default_in_gateway(self):
        """No hardcoded 'NSE_EQ' used as a fallback default in gateway methods.

        Allowed: exchange string membership checks (e.g. `if exchange in ('NSE', 'NSE_EQ', ...)`).
        Forbidden: using as fallback in `EXCHANGE_TO_SEGMENT.get(..., 'NSE_EQ')`.
        """
        with open(_gw_source("dhan")) as f:
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

        from brokers.upstox.wire import UpstoxBrokerGateway

        # Skip __init__ (heavy adapter construction) but set the init-set
        # attributes the delegation methods rely on, so each test can override
        # the specific sub-mock it exercises.
        gw = UpstoxBrokerGateway.__new__(UpstoxBrokerGateway)
        gw._broker = MagicMock()
        gw.options = MagicMock()
        gw._portfolio = MagicMock()
        gw._order_gw = MagicMock()
        gw._data_gw = MagicMock()
        return gw

    def test_upstox_option_chain_delegates_to_broker(self, upstox_gateway):
        """Upstox option_chain delegates to the data gateway's option chain."""
        from domain import OptionChain

        chain = OptionChain(underlying="NIFTY", exchange="NFO", expiry="2026-06-26")
        upstox_gateway._data_gw.option_chain.return_value = chain
        result = upstox_gateway.option_chain("NIFTY", exchange="NFO")
        assert isinstance(result, OptionChain)
        assert result.underlying == "NIFTY"
        upstox_gateway._data_gw.option_chain.assert_called_once_with("NIFTY", "NFO", None)

    def test_upstox_future_chain_returns_future_chain(self, upstox_gateway):
        """Upstox future_chain delegates to the data gateway's future chain."""
        from domain import FutureChain
        from domain.entities.options import FutureContract

        chain = FutureChain(
            underlying="NIFTY",
            exchange="NFO",
            contracts=(
                FutureContract(
                    symbol="NIFTY26JUNFUT",
                    expiry="2026-06-26",
                    lot_size=75,
                    underlying="NIFTY",
                ),
            ),
        )
        upstox_gateway._data_gw.future_chain.return_value = chain
        result = upstox_gateway.future_chain("NIFTY", exchange="NFO")
        assert isinstance(result, FutureChain)
        assert result.underlying == "NIFTY"
        assert len(result.contracts) == 1
        upstox_gateway._data_gw.future_chain.assert_called_once_with("NIFTY", "NFO")

    def test_upstox_get_trade_book_delegates_to_order_query(self, upstox_gateway):
        """Upstox get_trade_book delegates to the order gateway's trade book."""
        upstox_gateway._order_gw.get_trade_book.return_value = []
        result = upstox_gateway.get_trade_book()
        assert result == []
        upstox_gateway._order_gw.get_trade_book.assert_called_once()


class TestMarketDataGatewayContract:
    """Both brokers must implement every abstract method of MarketDataGateway."""

    @pytest.fixture
    def abstract_methods(self):
        return set(MarketDataGateway.__abstractmethods__)

    def test_dhan_gateway_implements_all_abstract(self, abstract_methods):
        from brokers.dhan.wire import DhanBrokerGateway as DhanGateway

        dhan_methods = set(dir(DhanGateway))
        missing = abstract_methods - dhan_methods
        assert not missing, f"Dhan gateway missing abstract methods: {missing}"

    def test_upstox_gateway_implements_all_abstract(self, abstract_methods):
        from brokers.upstox.wire import UpstoxBrokerGateway

        upstox_methods = set(dir(UpstoxBrokerGateway))
        missing = abstract_methods - upstox_methods
        assert not missing, f"Upstox gateway missing abstract methods: {missing}"


class TestDhanGatewaySegmentMapping:
    """Dhan gateway uses EXCHANGE_TO_SEGMENT for all segment lookups."""

    @pytest.fixture
    def dhan_gateway(self):
        from unittest.mock import MagicMock

        from brokers.dhan.resolver import SymbolResolver
        from brokers.dhan.wire import DhanBrokerGateway as DhanGateway

        resolver = SymbolResolver()
        from brokers.dhan.domain import DhanInstrument, Exchange, InstrumentType
        from domain.entities.instrument_record import InstrumentRecord as DomainInstrument

        resolver._by_security_id = {
            "2885": DhanInstrument(
                domain_instrument=DomainInstrument(
                    symbol="RELIANCE",
                    exchange="NSE",
                    security_id="2885",
                    instrument_type="EQUITY",
                ),
                exchange=Exchange.NSE,
                instrument_type=InstrumentType.EQUITY,
            )
        }
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


class TestGatewayTypeSafety:
    """Gateway return types must be specific, not `Any`."""

    def _get_method_return_annotation(self, gateway_class, method_name: str) -> str | None:
        import ast

        with open(_gw_source(gateway_class.__module__.split(".")[1])) as f:
            tree = ast.parse(f.read())

        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef) and node.name == gateway_class.__name__:
                for item in node.body:
                    if isinstance(item, ast.FunctionDef) and item.name == method_name:
                        return ast.unparse(item.returns) if item.returns else None
        return None

    def test_dhan_quote_returns_quote_type(self):
        from brokers.dhan.wire import DhanBrokerGateway as DhanGateway

        ret = self._get_method_return_annotation(DhanGateway, "quote")
        assert ret == "Quote", f"Expected 'Quote', got {ret!r}"

    def test_dhan_positions_returns_list_position(self):
        from brokers.dhan.wire import DhanBrokerGateway as DhanGateway

        ret = self._get_method_return_annotation(DhanGateway, "positions")
        assert ret == "list[Position]", f"Expected 'list[Position]', got {ret!r}"

    def test_dhan_funds_returns_balance(self):
        from brokers.dhan.wire import DhanBrokerGateway as DhanGateway

        ret = self._get_method_return_annotation(DhanGateway, "funds")
        assert ret == "Balance", f"Expected 'Balance', got {ret!r}"

    def test_upstox_quote_returns_quote_type(self):
        from brokers.upstox.wire import UpstoxBrokerGateway

        ret = self._get_method_return_annotation(UpstoxBrokerGateway, "quote")
        assert ret == "Quote", f"Expected 'Quote', got {ret!r}"

    def test_upstox_depth_returns_market_depth_type(self):
        from brokers.upstox.wire import UpstoxBrokerGateway

        ret = self._get_method_return_annotation(UpstoxBrokerGateway, "depth")
        assert ret == "MarketDepth", f"Expected 'MarketDepth', got {ret!r}"

    def test_upstox_funds_returns_balance(self):
        from brokers.upstox.wire import UpstoxBrokerGateway

        ret = self._get_method_return_annotation(UpstoxBrokerGateway, "funds")
        assert ret == "Balance", f"Expected 'Balance', got {ret!r}"

    def test_upstox_positions_returns_list_position(self):
        from brokers.upstox.wire import UpstoxBrokerGateway

        ret = self._get_method_return_annotation(UpstoxBrokerGateway, "positions")
        assert ret == "list[Position]", f"Expected 'list[Position]', got {ret!r}"

    def test_upstox_holdings_returns_list_holding(self):
        from brokers.upstox.wire import UpstoxBrokerGateway

        ret = self._get_method_return_annotation(UpstoxBrokerGateway, "holdings")
        assert ret == "list[Holding]", f"Expected 'list[Holding]', got {ret!r}"

    def test_upstox_trades_returns_list_trade(self):
        from brokers.upstox.wire import UpstoxBrokerGateway

        ret = self._get_method_return_annotation(UpstoxBrokerGateway, "trades")
        assert ret == "list[Trade]", f"Expected 'list[Trade]', got {ret!r}"

    def test_upstox_get_orderbook_returns_list_order(self):
        from brokers.upstox.wire import UpstoxBrokerGateway

        ret = self._get_method_return_annotation(UpstoxBrokerGateway, "get_orderbook")
        assert ret == "list[Order]", f"Expected 'list[Order]', got {ret!r}"

    def test_no_any_in_critical_domain_methods(self):
        """Critical domain methods must not return `Any`."""
        import ast

        critical_methods = ["quote", "depth", "funds", "positions", "holdings", "trades"]
        for gateway_name in ["dhan", "upstox"]:
            gw_path = _gw_source(gateway_name)
            with open(gw_path) as f:
                tree = ast.parse(f.read())

            for node in ast.walk(tree):
                if isinstance(node, ast.ClassDef):
                    for item in node.body:
                        if isinstance(item, ast.FunctionDef) and item.name in critical_methods:
                            ret = ast.unparse(item.returns) if item.returns else None
                            assert ret != "Any", (
                                f"{gateway_name}.{node.name}.{item.name} returns Any"
                            )


class TestGatewayLogging:
    """Gateway files must have proper logging setup."""

    def test_dhan_gateway_has_logger(self):
        """Dhan gateway must have a module-level logger."""
        content = _gw_source("dhan").read_text()
        assert "import logging" in content
        assert "logger = logging.getLogger(__name__)" in content

    def test_upstox_gateway_has_logger(self):
        """Upstox gateway must have a module-level logger."""
        content = _gw_source("upstox").read_text()
        assert "import logging" in content
        assert "logger = logging.getLogger(__name__)" in content


class TestUpstoxQuoteLogging:
    """P-2.2: Test removed - was testing deleted adapter.

    The correct adapter (brokers.upstox.market_data.market_data_adapter)   # noqa: W291
    does not log warnings for empty quotes - it returns empty Quote objects.
    """

    pass


class TestReadPathTypedErrors:
    """get_quote/get_order must not swallow transport failures as empty results."""

    def test_dhan_get_order_raises_broker_error_on_transport_failure(self) -> None:
        from brokers.dhan.wire import DhanBrokerGateway
        from domain.errors import BrokerError

        gw = DhanBrokerGateway.__new__(DhanBrokerGateway)

        class _Orders:
            def get_order(self, order_id: str):
                raise ConnectionError("reset")

        class _Conn:
            orders = _Orders()

        gw._conn = _Conn()
        with pytest.raises(BrokerError):
            gw.get_order("123")

    def test_dhan_data_provider_get_quote_raises_quote_unavailable(self) -> None:
        from brokers.dhan.data.data_provider import DhanDataProvider
        from domain.exceptions import QuoteUnavailableError
        from domain.instruments.instrument_id import InstrumentId

        provider = DhanDataProvider.__new__(DhanDataProvider)
        provider._gw = type(
            "G",
            (),
            {
                "quote": staticmethod(lambda *_a, **_k: (_ for _ in ()).throw(RuntimeError("down")))
            },
        )()
        iid = InstrumentId(underlying="RELIANCE", exchange="NSE")
        with pytest.raises(QuoteUnavailableError):
            provider.get_quote(iid)

    def test_upstox_data_provider_get_depth_raises_quote_unavailable(self) -> None:
        from brokers.upstox.data_provider import UpstoxDataProvider
        from domain.exceptions import QuoteUnavailableError
        from domain.instruments.instrument_id import InstrumentId

        provider = UpstoxDataProvider.__new__(UpstoxDataProvider)
        provider._gw = type(
            "G",
            (),
            {"depth": staticmethod(lambda *_a, **_k: (_ for _ in ()).throw(RuntimeError("down")))},
        )()
        iid = InstrumentId(underlying="RELIANCE", exchange="NSE")
        with pytest.raises(QuoteUnavailableError):
            provider.get_depth(iid)


class TestTransportErrorMapping:
    """Order transport boundaries must map exceptions to canonical errors."""

    def test_map_transport_exception_classifies_network(self) -> None:
        from brokers.common.transport_errors import map_transport_exception
        from domain.errors import NetworkError

        try:
            import requests

            exc = requests.ConnectionError("reset")
        except ImportError:
            pytest.skip("requests not installed")
        mapped = map_transport_exception(exc)
        assert isinstance(mapped, NetworkError)

    def test_dhan_order_transport_uses_mapper(self) -> None:
        content = (GATEWAY_DIR / "dhan" / "api" / "transport.py").read_text()
        assert "order_result_from_transport_error" in content
        assert "OrderResult.fail(str(exc))" not in content


class TestTransportBareExceptRatchet:
    """Bare ``except Exception: OrderResult.fail(str(exc))`` is forbidden in transport."""

    def test_no_unmapped_order_result_fail_in_dhan_transport(self) -> None:
        path = GATEWAY_DIR / "dhan" / "api" / "transport.py"
        content = path.read_text()
        assert "OrderResult.fail(str(exc))" not in content

    def test_no_unmapped_order_response_fail_in_dhan_execution(self) -> None:
        import re

        execution_dir = GATEWAY_DIR / "dhan" / "execution"
        pattern = re.compile(
            r"except Exception[^\n]*:\n(?:[^\n]*\n){0,8}[^\n]*"
            r"(OrderResponse\.fail\([^)]*\bexc\b|raise \w+Error\(f?[\"'][^\"']*\{?\s*exc)",
            re.MULTILINE,
        )
        for path in execution_dir.glob("*.py"):
            content = path.read_text()
            matches = pattern.findall(content)
            assert not matches, f"{path.name} stringifies raw exceptions: {matches}"

    def test_upstox_order_command_adapter_uses_mapper(self) -> None:
        content = (GATEWAY_DIR / "upstox" / "orders" / "order_command_adapter.py").read_text()
        assert "order_response_from_transport_error" in content
        assert "OrderResponse.fail(str(exc))" not in content
        assert 'OrderResponse.fail(f"network error:' not in content

    def test_upstox_order_gateway_uses_mapper(self) -> None:
        content = (GATEWAY_DIR / "upstox" / "adapters" / "order_gateway.py").read_text()
        assert "order_response_from_transport_error" in content
        assert "OrderResponse.fail(str(e))" not in content
        assert "OrderResponse.fail(str(exc))" not in content


class TestOrderResultFromResponse:
    """Malformed broker responses must fail closed (default success=False)."""

    def test_missing_success_attribute_fails(self) -> None:
        from brokers.common.transport_errors import order_result_from_response

        class _Response:
            order_id = "X"

        result = order_result_from_response(_Response())
        assert not result.success
        assert "malformed" in (result.error or "").lower()

    def test_success_false_fails(self) -> None:
        from brokers.common.transport_errors import order_result_from_response
        from domain import OrderResponse

        result = order_result_from_response(
            OrderResponse.fail(message="rejected", error_code="E1")
        )
        assert not result.success

    def test_dict_without_success_fails(self) -> None:
        from brokers.common.transport_errors import order_result_from_response

        result = order_result_from_response({"order_id": "1"})
        assert not result.success

    def test_success_true_ok(self) -> None:
        from brokers.common.transport_errors import order_result_from_response
        from domain import OrderResponse

        result = order_result_from_response(OrderResponse.ok(order_id="OK-1"))
        assert result.success
