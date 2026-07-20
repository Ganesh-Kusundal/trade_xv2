"""BrokerExtension — base re-export for broker-specific capability aggregators.

A broker extension aggregator collects a broker's concrete ``Extension``
implementations (depth20/200, super orders, news, …) so they can be stamped
onto instruments as ``instrument.broker.*``. The base SDK stays identical;
only the aggregator differs per broker.
"""

from __future__ import annotations

from typing import Any

from domain.extensions.base import Extension


class BrokerExtension:
    """Aggregates a broker's capability extensions for one instrument/session.

    Concrete broker plugins populate ``extensions`` with ``Extension`` objects.
    The facade binds them to an instrument via ``instrument.broker``.
    """

    broker_id: str = ""

    def __init__(self, *extensions: Extension) -> None:
        self.extensions: list[Extension] = list(extensions)

    def names(self) -> list[str]:
        return [str(getattr(e, "name", type(e).__name__)) for e in self.extensions]

    def for_instrument(self, instrument: Any) -> Any:
        """Return a bound broker facade over these extensions for ``instrument``."""
        from domain.extensions.facade import BrokerFacade

        return BrokerFacade(self.broker_id, list(self.extensions)).for_instrument(instrument)
