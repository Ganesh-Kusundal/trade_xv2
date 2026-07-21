#!/usr/bin/env python3
"""REST API data-source contract — manifest vs router module imports."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from domain.capability_manifest import CAPABILITY_SURFACES, RestExposure

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
        "get_session",
        "universe",
        "instrument",
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


def _check_router_module_matches_data_source(surface_id: str, rest: RestExposure) -> str | None:
    path = ROOT / rest.module
    if not path.is_file():
        return f"{surface_id}: missing router {rest.module}"
    if rest.data_source == "none":
        return None
    source = path.read_text(encoding="utf-8")
    hints = _DATA_SOURCE_IMPORT_HINTS.get(rest.data_source, ())
    if not any(h in source for h in hints):
        return (
            f"{surface_id} {rest.method} {rest.path}: "
            f"expected one of {hints} in {rest.module} for data_source={rest.data_source}"
        )
    return None


def _find_exposure(*, method: str | None = None, path: str | None = None) -> RestExposure | None:
    for surface in CAPABILITY_SURFACES:
        for rest in surface.rest:
            if path is not None and rest.path != path:
                continue
            if method is not None and rest.method != method:
                continue
            return rest
    return None


def main() -> int:
    violations: list[str] = []

    for surface_id, rest in _all_rest_exposures():
        err = _check_router_module_matches_data_source(surface_id, rest)
        if err:
            violations.append(err)

    quote = _find_exposure(path="/api/v1/market/quote/{symbol}")
    if quote is None:
        violations.append("missing REST exposure: GET /api/v1/market/quote/{symbol}")
    elif quote.data_source != "datalake":
        violations.append(f"quote endpoint data_source={quote.data_source}, expected datalake")

    orders_post = _find_exposure(method="POST", path="/api/v1/orders")
    if orders_post is None:
        violations.append("missing REST exposure: POST /api/v1/orders")
    elif orders_post.data_source != "live_broker":
        violations.append(f"orders POST data_source={orders_post.data_source}, expected live_broker")

    positions = _find_exposure(path="/api/v1/portfolio/positions")
    if positions is None:
        violations.append("missing REST exposure: /api/v1/portfolio/positions")
    elif positions.data_source != "oms":
        violations.append(f"positions data_source={positions.data_source}, expected oms")

    if violations:
        print("REST data-source contract violations:\n" + "\n".join(violations), file=sys.stderr)
        return 1

    n = len(_all_rest_exposures())
    print(f"OK: {n} REST exposures match declared data_source")
    return 0


if __name__ == "__main__":
    sys.exit(main())
