"""Injectable TLS session check — composition root wires infrastructure impl."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

_AssertSecure = Callable[[Any], None]
_assert_secure: _AssertSecure | None = None


def set_secure_session_asserter(fn: _AssertSecure) -> None:
    """Register assert_secure_session (composition root)."""
    global _assert_secure
    _assert_secure = fn


def assert_secure_session(session: Any) -> None:
    """Fail if session is not TLS-hardened; no-op checker raises if unwired."""
    if _assert_secure is None:
        raise RuntimeError(
            "Secure session asserter not registered. "
            "Call domain.ports.security.set_secure_session_asserter(...) at boot."
        )
    _assert_secure(session)
