"""Tests for the shared ``BaseWireAdapter`` liveness + delegation contract."""

from __future__ import annotations

from brokers.common.wire_base import BaseWireAdapter


class _FakeAdapter(BaseWireAdapter):
    """Minimal subclass exercising the base contract without broker deps."""

    broker_id = "fake"

    def __init__(self, transport_up: bool, trades: list) -> None:
        self._up = transport_up
        self._trades = trades

    def _transport_connected(self) -> bool:
        return self._up

    def get_trade_book(self) -> list:
        return self._trades


def test_base_is_connected_delegates_to_transport_hook() -> None:
    assert _FakeAdapter(transport_up=True, trades=[]).is_connected is True
    assert _FakeAdapter(transport_up=False, trades=[]).is_connected is False


def test_base_is_connected_swallows_hook_errors() -> None:
    class _Boom(BaseWireAdapter):
        broker_id = "boom"

        def _transport_connected(self) -> bool:
            raise RuntimeError("probe failed")

        def get_trade_book(self) -> list:
            return []

    assert _Boom().is_connected is False


def test_base_trades_delegates_to_trade_book() -> None:
    book = [object()]
    assert _FakeAdapter(transport_up=True, trades=book).trades() is book


def test_base_default_transport_is_conservatively_false() -> None:
    class _NoHook(BaseWireAdapter):
        broker_id = "nohook"

        def get_trade_book(self) -> list:
            return []

    # No override of _transport_connected -> must not report connected.
    assert _NoHook().is_connected is False
