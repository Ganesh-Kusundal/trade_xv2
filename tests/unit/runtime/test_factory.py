"""runtime.factory — ADR-017 composition root facade."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from runtime.factory import BuildOptions, build, build_from_broker_service
from runtime.trading_runtime_factory import Runtime


def test_build_requires_broker_service() -> None:
    with pytest.raises(ValueError, match="broker_service is required"):
        build(None)  # type: ignore[arg-type]


def test_build_delegates_to_trading_runtime_factory() -> None:
    bs = MagicMock()
    bs._active_name = "paper"
    expected = Runtime(
        broker_name="paper",
        gateway=None,
        trading_context=None,
        lifecycle=MagicMock(),
        oms_service=None,
        http_observability=None,
        readiness_report=None,
        live_actionable=False,
    )
    with patch(
        "runtime.factory.TradingRuntimeFactory.build_from_broker_service",
        return_value=expected,
    ) as build_fn:
        runtime = build(bs, mode="market", skip_parity_gate=True)
    build_fn.assert_called_once_with(bs)
    assert runtime is expected
    assert runtime.extra.get("mode") == "market"


def test_build_from_broker_service_forwards_options() -> None:
    bs = MagicMock()
    with patch("runtime.factory.TradingRuntimeFactory") as factory_cls:
        factory_cls.return_value.build_from_broker_service.return_value = MagicMock(
            spec=Runtime
        )
        build_from_broker_service(
            bs,
            options=BuildOptions(broker="upstox", skip_parity_gate=True),
        )
    factory_cls.assert_called_once_with(
        broker="upstox",
        authorize_risk_fail_open=False,
        env_path=None,
        wire_orchestrator=True,
        wire_intelligent_gateway=None,
        orchestrator_dry_run=None,
        skip_parity_gate=True,
        resilience=None,
    )