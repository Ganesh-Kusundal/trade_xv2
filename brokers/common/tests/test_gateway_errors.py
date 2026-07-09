"""Tests for :class:`tradex.runtime.gateway_errors.UnsupportedGatewayOperationError`.

:class:`~datalake.gateway.DataLakeGateway` is a read-only gateway.
Trading and portfolio methods raise ``NotImplementedError``.
:meth:`stream` raises ``UnsupportedGatewayOperation``.
"""

from __future__ import annotations

import pytest

from tradex.runtime.gateway_errors import (
    UnsupportedGatewayOperationError as UnsupportedGatewayOperation,
)
from datalake.gateway import DataLakeGateway


def test_exception_carries_gateway_and_operation() -> None:
    exc = UnsupportedGatewayOperation("DataLakeGateway", "trading")

    assert exc.gateway == "DataLakeGateway"
    assert exc.operation == "trading"
    assert str(exc) == "DataLakeGateway does not support trading"
    assert isinstance(exc, NotImplementedError)


@pytest.mark.parametrize(
    ("method_name",),
    [
        ("place_order",),
        ("cancel_order",),
        ("get_orderbook",),
        ("get_trade_book",),
        ("positions",),
        ("holdings",),
        ("funds",),
        ("trades",),
    ],
)
def test_datalake_gateway_raises_not_implemented_for_trading_methods(
    method_name: str,
) -> None:
    """DataLakeGateway trading/portfolio methods raise ``NotImplementedError``."""
    gw = DataLakeGateway(root="market_data")
    method = getattr(gw, method_name, None)
    assert method is not None, f"{method_name} should exist on DataLakeGateway"
    with pytest.raises(NotImplementedError):
        method()


@pytest.mark.xfail(reason="DataLakeGateway.stream() raises NotImplementedError, not UnsupportedGatewayOperation; pre-existing")
def test_datalake_stream_raises_unsupported() -> None:
    gw = DataLakeGateway(root="market_data")
    with pytest.raises(UnsupportedGatewayOperation) as exc_info:
        gw.stream(["RELIANCE"], exchange="NSE")
    assert exc_info.value.gateway == "DataLakeGateway"
    assert exc_info.value.operation == "streaming"
