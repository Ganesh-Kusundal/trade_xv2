"""Dhan connection settings — credentials from env or explicit ctor."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

# v2/.../dhan/config.py → parents[5] = repo root (share src runtime/ token + cooldown)
_REPO_RUNTIME = Path(__file__).resolve().parents[5] / "runtime"


@dataclass
class DhanConfig:
    client_id: str = ""
    access_token: str = ""
    pin: str = ""
    totp_secret: str = ""
    base_url: str = "https://api.dhan.co/v2"
    generate_token_url: str = "https://auth.dhan.co/app/generateAccessToken"
    ws_url: str = "wss://api-feed.dhan.co"
    token_path: Path = field(default_factory=lambda: _REPO_RUNTIME / "dhan-token-state.json")
    cooldown_path: Path = field(
        default_factory=lambda: _REPO_RUNTIME / "dhan-totp-cooldown.json"
    )
    token_ttl_seconds: float = 24 * 3600
    refresh_buffer_seconds: float = 300  # 5 minutes before expiry, trigger proactive refresh
    # Safety gate — live order placement refused unless explicitly enabled
    allow_live_orders: bool = False

    @classmethod
    def from_env(cls) -> DhanConfig:
        return cls(
            client_id=os.environ.get("DHAN_CLIENT_ID", ""),
            access_token=os.environ.get("DHAN_ACCESS_TOKEN", ""),
            pin=os.environ.get("DHAN_PIN", ""),
            totp_secret=os.environ.get("DHAN_TOTP_SECRET", ""),
            base_url=os.environ.get("DHAN_BASE_URL", "https://api.dhan.co/v2"),
            generate_token_url=os.environ.get(
                "DHAN_GENERATE_TOKEN_URL",
                "https://auth.dhan.co/app/generateAccessToken",
            ),
            ws_url=os.environ.get("DHAN_WS_URL", "wss://api-feed.dhan.co"),
            token_path=Path(
                os.environ.get("DHAN_TOKEN_PATH", str(_REPO_RUNTIME / "dhan-token-state.json"))
            ),
            cooldown_path=Path(
                os.environ.get(
                    "DHAN_COOLDOWN_PATH", str(_REPO_RUNTIME / "dhan-totp-cooldown.json")
                )
            ),
            allow_live_orders=os.environ.get("DHAN_ALLOW_LIVE_ORDERS", "").strip().lower()
            in {"1", "true", "yes", "on"},
        )

    @property
    def has_totp(self) -> bool:
        return bool(self.client_id and self.pin and self.totp_secret)
