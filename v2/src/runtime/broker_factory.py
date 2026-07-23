"""Build concrete broker gateways from AppConfig (composition-root only)."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

from config.schema import AppConfig
from domain.enums import BrokerId
from domain.ports.broker_adapter import BrokerAdapter
from plugins.brokers.dhan import DhanGateway
from plugins.brokers.dhan.config import DhanConfig
from plugins.brokers.paper import PaperGateway
from plugins.brokers.upstox import UpstoxGateway
from plugins.brokers.upstox.config import UpstoxConfig
from runtime.discovery import discover_brokers


def build_broker_adapter(
    config: AppConfig,
    *,
    transport: Any | None = None,
    ws_factory: Callable[[str], Any] | None = None,
) -> Any:
    """Resolve broker_id once and construct the gateway with credentials.

    Args:
        config: Application configuration with broker credentials
        transport: Optional injectable HTTP transport (for testing)
        ws_factory: Optional WebSocket factory function (for streaming)
    """
    discover_brokers()
    broker = config.broker
    gateway: Any
    if broker == BrokerId.PAPER:
        gateway = PaperGateway()
    elif broker == BrokerId.DHAN:
        d = config.dhan
        # merge env file credentials when AppConfig fields empty
        env_cfg = DhanConfig.from_env()
        cfg = DhanConfig(
            client_id=d.client_id or env_cfg.client_id,
            access_token=d.access_token or env_cfg.access_token,
            pin=d.pin or env_cfg.pin,
            totp_secret=d.totp_secret or env_cfg.totp_secret,
            base_url=d.base_url or env_cfg.base_url,
            token_path=Path(d.token_path) if d.token_path else env_cfg.token_path,
        )
        gateway = DhanGateway(config=cfg, transport=transport, ws_factory=ws_factory)
    elif broker == BrokerId.UPSTOX:
        u = config.upstox
        env_cfg = UpstoxConfig.from_env()
        cfg = UpstoxConfig(
            client_id=u.client_id or env_cfg.client_id,
            client_secret=u.client_secret or env_cfg.client_secret,
            access_token=u.access_token or env_cfg.access_token,
            refresh_token=u.refresh_token or env_cfg.refresh_token,
            mobile=u.mobile or env_cfg.mobile,
            pin=u.pin or env_cfg.pin,
            totp_secret=u.totp_secret or env_cfg.totp_secret,
            base_url=u.base_url or env_cfg.base_url,
            token_path=Path(u.token_path) if u.token_path else env_cfg.token_path,
        )
        gateway = UpstoxGateway(config=cfg, transport=transport, ws_factory=ws_factory)
    else:
        raise ValueError(f"unknown broker: {broker}")

    # Runtime Protocol enforcement: ensure gateway implements BrokerAdapter
    if not isinstance(gateway, BrokerAdapter):
        missing = [m for m in dir(BrokerAdapter) if not hasattr(gateway, m) and not m.startswith("_")]
        raise TypeError(
            f"{type(gateway).__name__} does not implement BrokerAdapter Protocol. "
            f"Missing methods: {missing}"
        )

    return gateway
