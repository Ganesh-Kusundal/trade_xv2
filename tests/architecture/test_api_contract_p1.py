"""Architecture ratchets for P1 audit fixes — idempotency, trades auth, extended block."""

from __future__ import annotations

import inspect

import pytest


@pytest.mark.architecture
def test_orders_place_resolves_idempotency_before_domain_mapping():
    from interface.api.routers import orders

    src = inspect.getsource(orders.place_order)
    assert "resolve_api_correlation_id" in src
    assert "IDEMPOTENCY_HEADER" in src
    assert "api:{uuid.uuid4()" not in src


@pytest.mark.architecture
def test_trades_router_declares_require_auth():
    from interface.api.routers import _trades

    src = inspect.getsource(_trades)
    assert "require_auth" in src
    assert "APIRouter(dependencies=[Depends(require_auth)])" in src.replace(" ", "")


@pytest.mark.architecture
def test_extended_order_mutations_require_spine_policy():
    from interface.api.routers.live import extended

    src = inspect.getsource(extended)
    assert "require_extended_order_spine_allowed" in src
    for route in (
        '"/orders/super"',
        '"/orders/forever"',
        '"/orders/exit-all"',
        '"/orders/gtt"',
    ):
        assert route in src
