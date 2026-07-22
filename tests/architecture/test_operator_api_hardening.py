"""ADR-0020 — Operator API hardening architecture ratchet."""

from __future__ import annotations

import inspect

import pytest


@pytest.mark.architecture
def test_orders_router_does_not_call_tradex_connect_per_request():
    from interface.api.routers import orders

    src = inspect.getsource(orders)
    assert "tradex.connect" not in src


@pytest.mark.architecture
def test_orders_router_does_not_use_asyncio_run():
    from interface.api.routers import orders

    src = inspect.getsource(orders)
    assert "asyncio.run" not in src


@pytest.mark.architecture
def test_api_lifecycle_exports_process_session_wiring():
    from interface.api import lifecycle

    assert hasattr(lifecycle, "wire_api_process_session")
    assert hasattr(lifecycle, "get_api_process_session")
    assert hasattr(lifecycle, "build_trading_context")


@pytest.mark.architecture
def test_create_app_wires_api_process_session():
    from interface.api import deps

    src = inspect.getsource(deps.initialize_all_services)
    assert "wire_api_process_session" in src


@pytest.mark.architecture
def test_auth_none_requires_dev_gate_outside_pytest():
    from interface.api import auth

    src = inspect.getsource(auth._auth_none_allowed)
    assert "TRADEX_DEV" in src
