"""BootstrapOptions — structured configuration for gateway bootstrap.

Reduces the 10-parameter ``bootstrap_gateway`` signature to a single
config object, making the configuration surface explicit.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class BootstrapOptions:
    """Configuration for :func:`infrastructure.gateway.factory.bootstrap_gateway`.

    Most fields have sensible defaults; callers only override what they need.
    """

    # ── Identity ──
    broker: str = "paper"
    env_path: str | Path | None = None

    # ── Instrument loading ──
    load_instruments: bool = True

    # ── Infrastructure injection ──
    event_bus: Any | None = None
    lifecycle: Any | None = None
    risk_manager: Any | None = None

    # ── Auth probe control ──
    # skip_auth_probe: Skip the network probe (transport only).
    skip_auth_probe: bool = False
    # require_authenticated: When False, skip probe. When True/None, run for live brokers.
    require_authenticated: bool | None = None
    # analytics_only: Legacy flag — implies skip probe.
    analytics_only: bool = False
    # skip_credential_check: Legacy flag — implies skip probe.
    skip_credential_check: bool = False
