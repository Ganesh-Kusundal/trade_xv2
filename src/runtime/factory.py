"""Single composition root facade (ADR-017).

Thin delegate over existing wiring paths. Entry points migrate here incrementally;
``TradingRuntimeFactory`` and ``tradex.open_session`` remain until zero usage.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from runtime.trading_runtime_factory import Runtime, TradingRuntimeFactory

RuntimeMode = Literal["trade", "market", "sim"]


@dataclass(frozen=True)
class BuildOptions:
    """Options for :func:`build`."""

    broker: str = "dhan"
    mode: RuntimeMode = "trade"
    authorize_risk_fail_open: bool = False
    env_path: Path | None = None
    wire_orchestrator: bool = True
    wire_intelligent_gateway: bool | None = None
    orchestrator_dry_run: bool | None = None
    skip_parity_gate: bool = False
    resilience: Any | None = None
    extra: dict[str, Any] = field(default_factory=dict)


def build_from_broker_service(
    broker_service: Any,
    *,
    options: BuildOptions | None = None,
) -> Runtime:
    """Build a :class:`Runtime` from an injected broker service (canonical API)."""
    opts = options or BuildOptions()
    factory = TradingRuntimeFactory(
        broker=opts.broker,
        authorize_risk_fail_open=opts.authorize_risk_fail_open,
        env_path=opts.env_path,
        wire_orchestrator=opts.wire_orchestrator,
        wire_intelligent_gateway=opts.wire_intelligent_gateway,
        orchestrator_dry_run=opts.orchestrator_dry_run,
        skip_parity_gate=opts.skip_parity_gate,
        resilience=opts.resilience,
    )
    runtime = factory.build_from_broker_service(broker_service)
    if opts.extra:
        runtime.extra.update(opts.extra)
    return runtime


def build(
    broker_service: Any,
    *,
    mode: RuntimeMode = "trade",
    broker: str | None = None,
    skip_parity_gate: bool | None = None,
    **kwargs: Any,
) -> Runtime:
    """Unified composition entry (ADR-017).

    Args:
        broker_service: Wired ``BrokerService`` from UI compose / API bootstrap.
        mode: Session mode hint stored on ``runtime.extra`` for callers.
        broker: Broker id override (defaults from service when omitted).
        skip_parity_gate: Override parity gate (defaults from env).
        **kwargs: Forwarded to :class:`BuildOptions` fields.
    """
    if broker_service is None:
        raise ValueError("broker_service is required for runtime.factory.build")
    if skip_parity_gate is None:
        skip_parity_gate = os.getenv("SKIP_PARITY_GATE", "0") == "1"
    broker_id = broker or getattr(broker_service, "_active_name", None) or "dhan"
    opts = BuildOptions(
        broker=str(broker_id),
        mode=mode,
        skip_parity_gate=skip_parity_gate,
        **{k: v for k, v in kwargs.items() if k in BuildOptions.__dataclass_fields__},
    )
    runtime = build_from_broker_service(broker_service, options=opts)
    runtime.extra.setdefault("mode", mode)
    return runtime