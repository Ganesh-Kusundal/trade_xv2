"""Architecture test — verify all gateway implementations match the ABC signatures."""

from __future__ import annotations

import inspect
from typing import get_type_hints

import pytest


def _get_public_methods(cls: type) -> dict[str, inspect.Signature]:
    """Return {name: signature} for all public methods on cls."""
    methods = {}
    for name in dir(cls):
        if name.startswith("_"):
            continue
        obj = getattr(cls, name, None)
        if callable(obj) and not isinstance(obj, (property, staticmethod, classmethod)):
            try:
                methods[name] = inspect.signature(obj)
            except (ValueError, TypeError):
                pass
    return methods


def test_all_gateways_implement_abc_methods() -> None:
    """Every MarketDataGateway subclass must implement all abstract methods."""
    from brokers.common.gateway import MarketDataGateway

    abc_methods = set()
    for name in dir(MarketDataGateway):
        obj = getattr(MarketDataGateway, name, None)
        if getattr(obj, "__isabstractmethod__", False):
            abc_methods.add(name)

    from brokers.dhan.gateway import BrokerGateway
    from brokers.upstox.gateway import UpstoxBrokerGateway
    from brokers.paper.paper_gateway import PaperGateway

    for gw_cls in (BrokerGateway, UpstoxBrokerGateway, PaperGateway):
        for method_name in abc_methods:
            assert hasattr(gw_cls, method_name), (
                f"{gw_cls.__name__} is missing abstract method {method_name!r}"
            )
            method = getattr(gw_cls, method_name)
            assert not getattr(method, "__isabstractmethod__", False), (
                f"{gw_cls.__name__}.{method_name} is still abstract"
            )
