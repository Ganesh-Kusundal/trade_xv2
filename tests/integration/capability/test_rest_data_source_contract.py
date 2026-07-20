"""REST API data-source contract tests — manifest vs router imports."""

from __future__ import annotations

from pathlib import Path

import pytest

from domain.capability_manifest import CAPABILITY_SURFACES, RestExposure

PROJECT_ROOT = Path(__file__).resolve().parents[2]

# Expected import tokens per data_source in router modules.
_DATA_SOURCE_IMPORT_HINTS: dict[str, tuple[str, ...]] = {
    "datalake": (
        "get_datalake_gateway",
        "datalake_gateway",
        "view_manager",
        "get_view_manager",
        "get_data_catalog",
        "data_catalog",
    ),
    "oms": (
        "get_order_manager",
        "get_position_repository",
        "get_risk_manager",
        "get_trading_context",
        "get_container",
        "trading_context",
    ),
    "live_broker": (
        "get_broker_service",
        "require_live_broker",
        "broker_service",
        "submit_order",
        "execution_service",
        "subscribe_symbols_to_broker",
        "feed_wiring",
        "get_event_bus",
        "get_execution_composer",
        "execution_composer",
        "composer",
    ),
    "none": (),
    "mixed": ("get_datalake_gateway", "get_trading_context", "get_view_manager"),
}


def _all_rest_exposures() -> list[tuple[str, RestExposure]]:
    result: list[tuple[str, RestExposure]] = []
    for surface in CAPABILITY_SURFACES:
        for rest in surface.rest:
            result.append((surface.id, rest))
    return result


class TestRestDataSourceContract:
    """Each REST exposure's declared data_source matches router module content."""

    @pytest.mark.parametrize(
        "surface_id,rest",
        _all_rest_exposures(),
        ids=[f"{sid}:{r.method}:{r.path}" for sid, r in _all_rest_exposures()],
    )
    def test_router_module_matches_data_source(self, surface_id: str, rest: RestExposure) -> None:
        path = PROJECT_ROOT / rest.module
        assert path.exists(), f"{surface_id}: missing router {rest.module}"
        source = path.read_text(encoding="utf-8")
        hints = _DATA_SOURCE_IMPORT_HINTS.get(rest.data_source, ())
        if rest.data_source == "none":
            return
        assert any(h in source for h in hints), (
            f"{surface_id} {rest.method} {rest.path}: "
            f"expected one of {hints} in {rest.module} for data_source={rest.data_source}"
        )

    def test_quote_rest_uses_datalake_not_live_broker(self) -> None:
        exposures = [
            r
            for s in CAPABILITY_SURFACES
            for r in s.rest
            if r.path == "/api/v1/market/quote/{symbol}"
        ]
        assert len(exposures) == 1
        assert exposures[0].data_source == "datalake"

    def test_orders_post_uses_live_broker(self) -> None:
        exposures = [
            r
            for s in CAPABILITY_SURFACES
            for r in s.rest
            if r.method == "POST" and r.path == "/api/v1/orders"
        ]
        assert len(exposures) == 1
        assert exposures[0].data_source == "live_broker"

    def test_portfolio_positions_uses_oms(self) -> None:
        exposures = [
            r
            for s in CAPABILITY_SURFACES
            for r in s.rest
            if r.path == "/api/v1/portfolio/positions"
        ]
        assert len(exposures) == 1
        assert exposures[0].data_source == "oms"
