"""Factory for building the initial token holder and typed holder instances.

Extracted from ``UpstoxTokenManager`` so holder construction is isolated from
the token lifecycle logic.
"""

from __future__ import annotations

from .holders import (
    UpstoxAnalyticsTokenHolder,
    UpstoxExtendedTokenHolder,
    UpstoxStaticTokenHolder,
    UpstoxTokenHolder,
)


class TokenHolderFactory:
    """Builds token holders from settings or explicit tokens."""

    def build_initial(self, settings: any) -> UpstoxTokenHolder:
        s = settings
        if s.analytics_only:
            return UpstoxAnalyticsTokenHolder(s.analytics_token or s.access_token)
        if s.is_extended and s.extended_token:
            return UpstoxExtendedTokenHolder(s.extended_token)
        if s.is_totp:
            # TOTP mode: placeholder, populated during bootstrap.
            return UpstoxStaticTokenHolder("placeholder-totp-will-refresh")
        if s.is_static or (s.access_token and not s.refresh_token):
            return UpstoxStaticTokenHolder(
                s.access_token,
                analytics_only=False,
                label="Upstox access token",
            )
        if s.access_token and s.refresh_token:
            return UpstoxStaticTokenHolder(
                s.access_token,
                analytics_only=False,
                label="Upstox access token (bootstrapped from refresh)",
            )
        return UpstoxStaticTokenHolder("placeholder-no-token")

    def extended(self, token: str) -> UpstoxExtendedTokenHolder:
        return UpstoxExtendedTokenHolder(token)

    def analytics(self, token: str) -> UpstoxAnalyticsTokenHolder:
        return UpstoxAnalyticsTokenHolder(token)

    def static(self, token: str) -> UpstoxStaticTokenHolder:
        return UpstoxStaticTokenHolder(token)
