"""Architecture — composer bootstrap must use bootstrap_gateway + wrap, not raw wire."""

from __future__ import annotations

import inspect

import pytest


@pytest.mark.architecture
def test_composer_helpers_does_not_construct_raw_wire() -> None:
    from interface.ui import composer_helpers

    source = inspect.getsource(composer_helpers)
    forbidden = (
        "from_env",
        "DhanBroker(",
        "UpstoxWireAdapter(",
        "PaperGateway()",
    )
    hits = [token for token in forbidden if token in source]
    assert not hits, (
        f"composer_helpers must bootstrap via bootstrap_gateway, not raw wire: {hits}"
    )


@pytest.mark.architecture
def test_composer_helpers_uses_bootstrap_and_wrap() -> None:
    from interface.ui import composer_helpers

    source = inspect.getsource(composer_helpers)
    assert "bootstrap_gateway" in source
    assert "wrap_market_gateway" in source
