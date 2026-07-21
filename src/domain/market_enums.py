"""Market and instrument taxonomy enums.

Submodule of :mod:`domain.types` — imported via the re-export facade.
"""

from __future__ import annotations

from enum import Enum


class ExchangeSegment(str, Enum):
    """Exchange segments supported by the broker system.

    The values use canonical wire-format strings (e.g. "NSE_EQ") so the
    segment string in the HTTP payload matches what the broker expects.
    """

    NSE = "NSE_EQ"
    BSE = "BSE_EQ"
    NSE_FNO = "NSE_FNO"
    BSE_FNO = "BSE_FNO"
    MCX = "MCXCOMM"
    NSE_CURRENCY = "NSE_CURRENCY"
    BSE_CURRENCY = "BSE_CURRENCY"
    IDX_I = "IDX_I"


class Exchange(str, Enum):
    """Short exchange codes used in broker APIs and instrument metadata."""

    NSE = "NSE"
    BSE = "BSE"
    NFO = "NFO"
    BFO = "BFO"
    MCX = "MCX"
    CDS = "CDS"
    INDEX = "INDEX"


class ExchangeId(str, Enum):
    """Canonical exchange identifiers used as default parameter values.

    Distinct from :class:`Exchange` — this enum is the single source of
    truth for ``"NSE"`` / ``"NFO"`` / etc. default arguments across the
    codebase, replacing scattered hardcoded string literals.
    """

    NSE = "NSE"
    NFO = "NFO"
    BSE = "BSE"
    MCX = "MCX"
    UNKNOWN = "UNKNOWN"


class InstrumentType(str, Enum):
    """Canonical instrument type categories."""

    EQUITY = "EQUITY"
    FUTURES = "FUTURES"
    FUTURE = "FUTURE"
    OPTIONS = "OPTIONS"
    OPTION = "OPTION"
    CURRENCY = "CURRENCY"
    COMMODITY = "COMMODITY"
    INDEX = "INDEX"


class OptionType(str, Enum):
    """Option flavour — CALL or PUT."""

    CALL = "CALL"
    PUT = "PUT"
