"""Shared base for broker wire adapters.

Both :class:`~brokers.providers.dhan.wire.DhanWireAdapter` and
:class:`~brokers.providers.upstox.wire.UpstoxWireAdapter` implement the same
``BrokerAdapter`` port but historically duplicated transport-agnostic behavior
and — critically — diverged on the meaning of ``is_connected``:

* Dhan reported WS-feed liveness and fell back to ``False`` when no feed existed
  (so a healthy REST-only session looked disconnected).
* Upstox reported a post-bootstrap status flag that was ``True`` even when the
  token was actually expired.

This base pins ONE liveness contract: ``is_connected`` means "the session is
authenticated and its primary transport is alive". Each subclass supplies that
verdict via ``_transport_connected()``; everything else shared lives here too.

Kept import-light and NOT an ABC so it is purely additive — neither subclass has
to change its ``__init__`` signature to inherit from it.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


class BaseWireAdapter:
    """Common surface for broker wire adapters (transport boundary).

    Subclasses MUST set ``broker_id`` and SHOULD override
    ``_transport_connected()``. They inherit ``is_connected`` (delegating to that
    hook) and ``trades()`` (delegating to ``get_trade_book()``).
    """

    # Each concrete adapter sets this (e.g. "dhan", "upstox", "paper").
    broker_id: str = ""
    #: Set False when factory connect/bootstrap failed so callers can distinguish
    #: a degraded gateway from a healthy authenticated session.
    bootstrap_transport_ready: bool = True

    # ── Connection liveness (unified contract) ──────────────────────────

    def _transport_connected(self) -> bool:
        """Subclass hook: report real transport/authentication liveness.

        Return ``True`` only when the session is authenticated and its primary
        transport is usable. The default is conservative (``False``) so a missing
        override never silently reports a healthy connection.
        """
        return False

    @property
    def is_connected(self) -> bool:
        """BrokerAdapter liveness contract — identical meaning for every broker.

        Means: authenticated + primary transport alive. Delegates to the
        subclass-supplied ``_transport_connected()`` hook.
        """
        try:
            return bool(self._transport_connected())
        except Exception as exc:  # pragma: no cover - defensive
            logger.debug("is_connected_probe_failed: %s", exc)
            return False

    # ── Shared, byte-identical behavior ─────────────────────────────────

    def trades(self) -> list[Any]:
        """Trade book — every broker derives it from ``get_trade_book``."""
        return self.get_trade_book()
