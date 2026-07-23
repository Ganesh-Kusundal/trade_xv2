"""BrokerExtensions — broker-unique capabilities looked up by type, no protocol bloat."""

from __future__ import annotations

import pytest

from plugins.brokers.common.extensions import BrokerExtensions
from plugins.brokers.dhan import DhanGateway
from plugins.brokers.paper import PaperGateway
from plugins.brokers.upstox import UpstoxGateway


class _SuperOrderExtension:
    def place_super_order(self) -> str:
        return "placed"


class _EdisExtension:
    pass


def test_register_then_get_by_type() -> None:
    exts = BrokerExtensions()
    ext = _SuperOrderExtension()
    exts.register(ext)

    assert exts.get(_SuperOrderExtension) is ext


def test_get_missing_extension_raises_lookup_error_with_available_names() -> None:
    exts = BrokerExtensions(_SuperOrderExtension())
    with pytest.raises(LookupError, match="_SuperOrderExtension"):
        exts.get(_EdisExtension)


def test_get_on_empty_registry_reports_none_available() -> None:
    exts = BrokerExtensions()
    with pytest.raises(LookupError, match="none"):
        exts.get(_SuperOrderExtension)


def test_names_lists_registered_extension_type_names() -> None:
    exts = BrokerExtensions(_SuperOrderExtension(), _EdisExtension())
    assert exts.names() == ["_SuperOrderExtension", "_EdisExtension"]


class TestGatewayExtensionSeam:
    """Every gateway exposes the same extension() lookup, empty until registered."""

    def test_dhan_gateway_extension_seam(self) -> None:
        gw = DhanGateway.__new__(DhanGateway)
        gw.extensions = BrokerExtensions()
        with pytest.raises(LookupError):
            gw.extension(_SuperOrderExtension)
        ext = gw.extensions.register(_SuperOrderExtension())
        assert gw.extension(_SuperOrderExtension) is ext

    def test_upstox_gateway_extension_seam(self) -> None:
        gw = UpstoxGateway.__new__(UpstoxGateway)
        gw.extensions = BrokerExtensions()
        with pytest.raises(LookupError):
            gw.extension(_SuperOrderExtension)

    def test_paper_gateway_extension_seam(self) -> None:
        gw = PaperGateway.__new__(PaperGateway)
        gw.extensions = BrokerExtensions()
        with pytest.raises(LookupError):
            gw.extension(_SuperOrderExtension)
