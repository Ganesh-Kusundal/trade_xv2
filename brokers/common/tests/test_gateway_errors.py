"""Tests for :class:`brokers.common.gateway_errors.UnsupportedGatewayOperation`."""

from __future__ import annotations

import pytest

from brokers.common.gateway_errors import UnsupportedGatewayOperation
from datalake.gateway import DataLakeGateway


def test_exception_carries_gateway_and_operation() -> None:
    exc = UnsupportedGatewayOperation("DataLakeGateway", "trading")

    assert exc.gateway == "DataLakeGateway"
    assert exc.operation == "trading"
    assert str(exc) == "DataLakeGateway does not support trading"
    assert isinstance(exc, NotImplementedError)


@pytest.mark.parametrize(
    ("method_name", "operation"),
    [
        ("place_order", "trading"),
        ("cancel_order", "trading"),
        ("get_orderbook", "trading"),
        ("get_trade_book", "trading"),
        ("positions", "portfolio"),
        ("holdings", "portfolio"),
        ("funds", "portfolio"),
        ("trades", "portfolio"),
    ],
)
def test_datalake_gateway_raises_unsupported(method_name: str, operation: str) -> None:
    gw = DataLakeGateway(root="market_data")
    method = getattr(gw, method_name)

    with pytest.raises(UnsupportedGatewayOperation) as exc_info:
        if method_name in {"place_order", "cancel_order"}:
            method("SYM", exchange="NSE")
        else:
            method()

    assert exc_info.value.gateway == "DataLakeGateway"
    assert exc_info.value.operation == operation


def test_datalake_stream_raises_unsupported() -> None:
    gw = DataLakeGateway(root="market_data")
    with pytest.raises(UnsupportedGatewayOperation) as exc_info:
        gw.stream(["RELIANCE"], exchange="NSE")
    assert exc_info.value.gateway == "DataLakeGateway"
    assert exc_info.value.operation == "streaming"
