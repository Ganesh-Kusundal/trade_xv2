"""TokenLifecycle — shared token refresh / proactive-refresh / 401-retry mechanism.

Canonical implementation lives in :class:`infrastructure.auth.token.AuthManager`
(maps to Trade_J ``TokenLifecycleService``). This module re-exports it under the
kernel name so broker auth modules depend on one import path.

Per-broker ``auth.py`` modules supply only OAuth/TOTP/PKCE wire specifics and
inject ``on_acquire`` / ``on_refresh`` callbacks into :class:`TokenLifecycle`.
"""

from __future__ import annotations

from infrastructure.auth.token import AuthManager as TokenLifecycle

__all__ = ["TokenLifecycle"]
