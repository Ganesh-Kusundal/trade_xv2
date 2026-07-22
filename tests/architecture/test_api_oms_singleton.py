"""P0-1 — API bootstrap must share TradingContext OrderManager with ExecutionComposer."""

from __future__ import annotations

import inspect

import pytest


@pytest.mark.architecture
def test_bootstrap_passes_order_manager_to_create_composers_from_infra():
    from interface.api import bootstrap

    src = inspect.getsource(bootstrap.initialize_api_services)
    assert "order_manager=order_manager" in src


@pytest.mark.architecture
def test_bootstrap_order_manager_from_trading_context():
    from interface.api import bootstrap

    src = inspect.getsource(bootstrap.initialize_api_services)
    assert "trading_context.order_manager" in src
