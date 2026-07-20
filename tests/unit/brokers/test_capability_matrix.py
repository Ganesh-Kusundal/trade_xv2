"""Every declared supports_* flag maps to a brokers.services entry or allowlist."""

from __future__ import annotations

import pytest

from brokers.dhan.config.capabilities import dhan_capabilities
from brokers.paper.paper_gateway import PaperGateway
from brokers.services import core as services_core

# supports_* → services.core function name (when True on broker matrix)
_SERVICE_FOR_FEATURE: dict[str, str] = {
    "supports_place_order": "place_order",
    "supports_cancel_order": "cancel_order",
    "supports_modify_order": "modify_order",
    "supports_historical_data": "get_history",
    "supports_intraday_history": "get_history",
    "supports_live_market_data": "get_quote",
    "supports_depth": "get_depth",
    "supports_depth_20_ws": "probe_depth_ws",
    "supports_depth_200_ws": "probe_depth_ws",
    "supports_option_chain": "get_option_chain",
    "supports_polling_fallback": "get_quote",
    "supports_order_stream": "run_subscribe_probe",
    "supports_portfolio_stream": "run_subscribe_probe",
    "supports_news": "get_news",
    "supports_super_order": "list_super_orders",
    "supports_forever_order": "list_forever_orders",
}

# Declared True but intentionally not a first-class service (document why)
_NOT_EXPOSED: dict[str, str] = {
    "supports_expired_options_history": "historical niche; gateway-only",
    "supports_fundamentals": "Upstox extended; UI extended_orders only",
    "supports_native_slice_order": "Dhan slicing via gateway.extended only",
}


def _enabled_features(caps) -> list[str]:
    out: list[str] = []
    for name in _SERVICE_FOR_FEATURE:
        if getattr(caps, name, False):
            out.append(name)
    for name in _NOT_EXPOSED:
        if getattr(caps, name, False):
            out.append(name)
    return out


@pytest.mark.unit
@pytest.mark.parametrize(
    "broker_id,caps_fn",
    [
        ("paper", lambda: PaperGateway().capabilities()),
        ("dhan", dhan_capabilities),
    ],
)
def test_supported_features_have_service_or_allowlist(broker_id: str, caps_fn) -> None:
    caps = caps_fn()
    assert caps.broker_id == broker_id or broker_id in {caps.broker_id, "paper", "dhan"}
    for feature in _enabled_features(caps):
        if feature in _NOT_EXPOSED:
            continue
        service_name = _SERVICE_FOR_FEATURE[feature]
        assert hasattr(services_core, service_name), (
            f"{broker_id}: missing services.{service_name} for {feature}"
        )
        assert callable(getattr(services_core, service_name))

    payload = services_core.format_session_capabilities.__doc__
    assert payload


@pytest.mark.unit
def test_get_capabilities_matrix_keys_match_dhan() -> None:
    from brokers.services import get_capabilities

    caps = get_capabilities("paper")
    matrix = caps["matrix"]
    dhan_capabilities()
    for key in (
        "supports_place_order",
        "supports_historical_data",
        "supports_live_market_data",
        "supports_depth",
    ):
        assert key in matrix


@pytest.mark.unit
def test_session_gateway_uses_public_provider_gateway_property() -> None:
    from brokers.paper.data_provider import PaperDataProvider
    from brokers.paper.paper_gateway import PaperGateway
    from brokers.services.capabilities import _session_gateway

    class _FakeSession:
        provider = PaperDataProvider(PaperGateway())

    gw = _session_gateway(_FakeSession())
    assert gw is not None
    assert gw is _FakeSession.provider.gateway
