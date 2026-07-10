"""Dhan auth wire specifics — token acquisition against shared TokenLifecycle.

OAuth/TOTP details stay here; refresh/proactive-refresh/401-retry mechanism
lives in ``infrastructure.auth.token_lifecycle.TokenLifecycle``.
"""

from __future__ import annotations

from collections.abc import Callable

from infrastructure.auth.token_lifecycle import TokenLifecycle


def build_dhan_token_lifecycle(
    client_id: str,
    *,
    on_acquire: Callable[[], str] | None = None,
    on_refresh: Callable[[], str] | None = None,
    token_store=None,
) -> TokenLifecycle:
    """Construct a TokenLifecycle wired with Dhan-specific acquire/refresh."""
    return TokenLifecycle(
        client_id=client_id,
        token_store=token_store,
        on_acquire=on_acquire,
        on_refresh=on_refresh,
    )


__all__ = ["build_dhan_token_lifecycle"]
