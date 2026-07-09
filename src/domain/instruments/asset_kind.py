"""AssetKind — explicit instrument classification (PR-5).

Factories set kind on :class:`InstrumentId`; ``asset_type`` prefers kind over
name heuristics so ETF / commodity / spot are first-class without stringly types.
"""

from __future__ import annotations

from enum import Enum


class AssetKind(str, Enum):
    EQUITY = "EQUITY"
    INDEX = "INDEX"
    FUTURES = "FUTURES"
    OPTIONS = "OPTIONS"
    ETF = "ETF"
    CURRENCY = "CURRENCY"
    COMMODITY = "COMMODITY"
    SPOT = "SPOT"
    CRYPTO = "CRYPTO"
    BOND = "BOND"
    SYNTHETIC = "SYNTHETIC"

    @classmethod
    def parse(cls, value: str | AssetKind | None) -> AssetKind | None:
        if value is None:
            return None
        if isinstance(value, AssetKind):
            return value
        key = str(value).strip().upper()
        # Accept legacy "FUTURE" / "OPTION"
        aliases = {
            "FUTURE": cls.FUTURES,
            "FUTURES": cls.FUTURES,
            "OPTION": cls.OPTIONS,
            "OPTIONS": cls.OPTIONS,
        }
        if key in aliases:
            return aliases[key]
        try:
            return cls(key)
        except ValueError:
            return None
