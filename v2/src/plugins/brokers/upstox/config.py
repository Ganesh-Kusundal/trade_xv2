"""Upstox connection settings."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

# Share src runtime/ token + cooldown (probe-before-mint across v1/v2)
_REPO_RUNTIME = Path(__file__).resolve().parents[5] / "runtime"


@dataclass
class UpstoxConfig:
    client_id: str = ""
    client_secret: str = ""
    access_token: str = ""
    refresh_token: str = ""
    mobile: str = ""
    pin: str = ""
    totp_secret: str = ""
    redirect_uri: str = "http://localhost:3000"
    base_url: str = "https://api.upstox.com/v2"
    base_hft: str = "https://api-hft.upstox.com/v3"
    token_url: str = "https://api.upstox.com/v2/login/authorization/token"
    ws_url: str = "wss://api.upstox.com/v2/feed/market-data-feed"
    token_path: Path = field(default_factory=lambda: _REPO_RUNTIME / "upstox-token-state.json")
    cooldown_path: Path = field(
        default_factory=lambda: _REPO_RUNTIME / "upstox-totp-cooldown.json"
    )
    # OAuth proactive refresh only — TOTP must never mint early (src allow_proactive=False)
    refresh_buffer_seconds: float = 30 * 60
    # Safety gate — live order placement refused unless explicitly enabled
    allow_live_orders: bool = False

    @classmethod
    def from_env(cls) -> UpstoxConfig:
        # LIVE TOTP apps usually register API_KEY as OAuth client_id
        client_id = os.environ.get("UPSTOX_API_KEY") or os.environ.get("UPSTOX_CLIENT_ID", "")
        client_secret = os.environ.get("UPSTOX_API_SECRET") or os.environ.get(
            "UPSTOX_CLIENT_SECRET", ""
        )
        return cls(
            client_id=client_id,
            client_secret=client_secret,
            access_token=os.environ.get("UPSTOX_ACCESS_TOKEN", ""),
            refresh_token=os.environ.get("UPSTOX_REFRESH_TOKEN", ""),
            mobile=os.environ.get("UPSTOX_MOBILE", ""),
            pin=os.environ.get("UPSTOX_PIN", ""),
            totp_secret=os.environ.get("UPSTOX_TOTP_SECRET", ""),
            redirect_uri=os.environ.get("UPSTOX_REDIRECT_URI", "http://localhost:3000"),
            base_url=os.environ.get("UPSTOX_BASE_URL", "https://api.upstox.com/v2"),
            base_hft=os.environ.get("UPSTOX_HFT_BASE_URL", "https://api-hft.upstox.com/v3"),
            token_path=Path(
                os.environ.get(
                    "UPSTOX_TOKEN_PATH", str(_REPO_RUNTIME / "upstox-token-state.json")
                )
            ),
            cooldown_path=Path(
                os.environ.get(
                    "UPSTOX_COOLDOWN_PATH", str(_REPO_RUNTIME / "upstox-totp-cooldown.json")
                )
            ),
            allow_live_orders=os.environ.get("UPSTOX_ALLOW_LIVE_ORDERS", "").strip().lower()
            in {"1", "true", "yes", "on"},
        )

    @property
    def has_totp(self) -> bool:
        return bool(self.mobile and self.pin and self.totp_secret and self.client_id)
