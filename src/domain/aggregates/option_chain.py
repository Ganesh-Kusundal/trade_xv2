"""OptionChain Aggregate — deprecated, use domain.options.option_chain.OptionChain instead.

This module is kept for backward compatibility.
OptionChainAggregate is now an alias for OptionChain, which has all the
query methods (atm, itm, otm, pcr, max_pain, etc.).
"""

from __future__ import annotations

import warnings

from domain.options.option_chain import OptionChain

warnings.warn(
    "domain.aggregates.option_chain.OptionChainAggregate is deprecated; "
    "use 'from domain.options.option_chain import OptionChain' instead.",
    DeprecationWarning,
    stacklevel=2,
)

# Backward-compatible alias
OptionChainAggregate = OptionChain

__all__ = ["OptionChainAggregate"]
