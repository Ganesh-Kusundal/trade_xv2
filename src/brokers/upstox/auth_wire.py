"""Upstox auth wire specifics — OAuth/TOTP against shared TokenLifecycle."""

from __future__ import annotations

from collections.abc import Callable

from infrastructure.auth.token_lifecycle import TokenLifecycle


def build_upstox_token_lifecycle(
    client_id: str,
    *,
    on_acquire: Callable[[], str] | None = None,
    on_refresh: Callable[[], str] | None = None,
    token_store=None,
) -> TokenLifecycle:
    return TokenLifecycle(
        client_id=client_id,
        token_store=token_store,
        on_acquire=on_acquire,
        on_refresh=on_refresh,
    )


__all__ = ["build_upstox_token_lifecycle"]
