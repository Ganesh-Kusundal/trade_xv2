"""Build concrete broker gateways from AppConfig (composition-root only)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from config.schema import AppConfig
from plugins.brokers.dhan import DhanGateway
from plugins.brokers.dhan.config import DhanConfig
from plugins.brokers.paper import PaperGateway
from plugins.brokers.upstox import UpstoxGateway
from plugins.brokers.upstox.config import UpstoxConfig
from runtime.discovery import discover_brokers


def build_broker_adapter(config: AppConfig, *, transport: Any | None = None) -> Any:
    """Resolve broker_id once and construct the gateway with credentials."""
    discover_brokers()
    broker = config.broker
    if broker == "paper":
        return PaperGateway()
    if broker == "dhan":
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
        return DhanGateway(config=cfg, transport=transport)
    if broker == "upstox":
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
        return UpstoxGateway(config=cfg, transport=transport)
    raise ValueError(f"unknown broker: {broker}")
