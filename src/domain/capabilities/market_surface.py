"""MarketCoverage — declarative asset/exchange coverage for a broker.

A :class:`MarketCoverage` is one (asset_kind, exchange) lane a broker can serve,
with a ``probe_symbol`` used by the shared coverage contract and the set of
``operations`` that lane supports (resolve/quote/ltp/option_chain/future_chain).

This is the single source of truth for *market* coverage. ``BrokerCapabilities``
owns a ``market_surfaces`` frozenset; the shared ``MarketCoverageContract``
iterates it so adding a broker or exchange is a data edit, never a new
broker-name branch in test or routing code.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from domain.instruments.asset_kind import AssetKind

# Operations a market coverage lane may expose.
RESOLVE = "resolve"
QUOTE = "quote"
LTP = "ltp"
OPTION_CHAIN = "option_chain"
FUTURE_CHAIN = "future_chain"

OPERATIONS = frozenset({RESOLVE, QUOTE, LTP, OPTION_CHAIN, FUTURE_CHAIN})


@dataclass(frozen=True)
class MarketCoverage:
    """One market lane a broker serves.

    asset_kind   — domain asset classification (EQUITY/INDEX/OPTIONS/FUTURES/SPOT/COMMODITY).
    exchange     — canonical short code (NSE/NFO/MCX/CDS/...); use
                   ``domain.constants.exchanges`` values, never raw literals.
    probe_symbol — a liquid instrument on this lane used by offline/live checks.
    operations   — frozenset of supported operations from ``OPERATIONS``.
    """

    asset_kind: AssetKind
    exchange: str
    probe_symbol: str
    operations: frozenset[str] = field(default_factory=frozenset)

    def supports_operation(self, operation: str) -> bool:
        return operation in self.operations


__all__ = [
    "FUTURE_CHAIN",
    "LTP",
    "OPERATIONS",
    "OPTION_CHAIN",
    "QUOTE",
    "RESOLVE",
    "MarketCoverage",
]
