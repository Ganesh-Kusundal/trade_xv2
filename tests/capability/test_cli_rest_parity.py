"""CLI live_readonly endpoints must have matching /api/v1/live/* REST routes."""

from __future__ import annotations

import pytest

from cli.tests.endpoint_manifest import LIVE_READONLY_ENDPOINTS, CliEndpoint
from domain.capability_manifest import CAPABILITY_SURFACES, surface_by_id

# Map capability_id -> expected live REST path templates.
_LIVE_REST_BY_CAPABILITY: dict[str, str] = {
    "market_data.quote": "/api/v1/live/quote/{symbol}",
    "market_data.depth": "/api/v1/live/depth/{symbol}",
    "market_data.history": "/api/v1/live/candles",
    "derivatives.option_chain": "/api/v1/live/options/chain/{underlying}",
    "derivatives.future_chain": "/api/v1/live/futures/chain/{underlying}",
    "portfolio.positions": "/api/v1/live/positions",
    "portfolio.holdings": "/api/v1/live/holdings",
    "portfolio.funds": "/api/v1/live/funds",
    "orders.query_orderbook": "/api/v1/live/orders",
    "orders.query_trades": "/api/v1/live/trades",
}


def _manifest_live_paths() -> set[str]:
    paths: set[str] = set()
    for surface in CAPABILITY_SURFACES:
        for rest in surface.rest:
            if rest.data_source == "live_broker" and rest.path.startswith("/api/v1/live"):
                paths.add(rest.path)
    return paths


@pytest.mark.parametrize(
    "endpoint",
    [
        e
        for e in LIVE_READONLY_ENDPOINTS
        if e.capability_id in _LIVE_REST_BY_CAPABILITY and not e.no_subprocess
    ],
    ids=lambda e: e.id,
)
def test_live_readonly_cli_has_rest_twin(endpoint: CliEndpoint) -> None:
    assert endpoint.capability_id is not None
    expected = _LIVE_REST_BY_CAPABILITY[endpoint.capability_id]
    surface = surface_by_id(endpoint.capability_id)
    assert surface is not None
    live_paths = {r.path for r in surface.rest if r.data_source == "live_broker"}
    assert expected in live_paths, (
        f"CLI {endpoint.id} ({endpoint.capability_id}) missing live REST twin {expected}"
    )


def test_manifest_live_routes_registered() -> None:
    live_paths = _manifest_live_paths()
    for expected in _LIVE_REST_BY_CAPABILITY.values():
        assert expected in live_paths, f"Missing manifest live route {expected}"
