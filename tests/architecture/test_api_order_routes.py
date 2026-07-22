"""Architecture ratchet — API order route wiring invariants."""

from __future__ import annotations

import inspect

import pytest


@pytest.mark.architecture
def test_cancel_modify_route_directly_through_composer():
    """P0-4: cancel/modify must not double-nest OMS via om.* wrapper callbacks."""
    from interface.api.routers import orders

    src = inspect.getsource(orders.cancel_order)
    assert "om.cancel_order" not in src

    src = inspect.getsource(orders.modify_order)
    assert "om.modify_order" not in src
