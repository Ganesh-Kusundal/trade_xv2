"""Port for session creation — application layer depends on this, not on tradex."""

from __future__ import annotations

from collections.abc import Callable

from domain.universe import Session as DomainSession

SessionOpener = Callable[..., DomainSession]
