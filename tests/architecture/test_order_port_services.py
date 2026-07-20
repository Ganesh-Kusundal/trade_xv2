"""SS-02 — broker services use OrderPlacementPort when gateway exposes it."""

from __future__ import annotations

from unittest.mock import patch

from domain.ports.order_placement import OrderPlacementPort


def test_order_port_from_session_none_without_gateway() -> None:
    from brokers.services.order_port import order_port_from_session

    with patch("brokers.services.order_port._session_gateway", return_value=None):
        assert order_port_from_session(object()) is None


def test_order_port_from_session_returns_gateway_with_place_order() -> None:
    from brokers.services.order_port import order_port_from_session

    class _Gw:
        def place_order(self, *args, **kwargs):
            return {"ok": True}

    with patch("brokers.services.order_port._session_gateway", return_value=_Gw()):
        port = order_port_from_session(object())
        assert port is not None
        assert isinstance(port, OrderPlacementPort)
