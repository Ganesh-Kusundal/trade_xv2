"""Derivatives bounded context — futures + options.

Re-exports the canonical types so callers can import from one place::

    from domain.derivatives import Future, OptionChain, Greeks
"""

from __future__ import annotations

from domain.entities.options import FutureChain, FutureContract, OptionChain, OptionContract, OptionLeg, OptionStrike
from domain.instruments.instrument import Future, Option
from domain.options.greeks import Greeks
from domain.options.option_chain import OptionChain as OptionChainAggregate

__all__ = [
    "Future",
    "FutureChain",
    "FutureContract",
    "Greeks",
    "Option",
    "OptionChain",
    "OptionChainAggregate",
    "OptionContract",
    "OptionLeg",
    "OptionStrike",
]
