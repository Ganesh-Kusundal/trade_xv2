"""Corporate actions — split price adjustment.

ponytail: in-memory split ratios only; persist later if multi-session needed.
"""

from __future__ import annotations


class CorporateActionStore:
    """Adjust prices for stock splits (ratio = new shares per old share)."""

    def __init__(self) -> None:
        self._splits: dict[str, float] = {}

    def record_split(self, symbol: str, ratio: float) -> None:
        if ratio <= 0:
            raise ValueError(f"split ratio must be positive, got {ratio}")
        self._splits[symbol] = ratio

    def adjust_price(
        self,
        price: float,
        ratio: float | None = None,
        *,
        symbol: str | None = None,
    ) -> float:
        """Backward-adjust price for a split: price / ratio.

        Prefer explicit ``ratio``; else look up ``symbol`` from recorded splits.
        """
        if ratio is None:
            if symbol is None:
                raise ValueError("ratio or symbol required")
            ratio = self._splits.get(symbol)
            if ratio is None:
                raise KeyError(f"no split recorded for {symbol}")
        if ratio <= 0:
            raise ValueError(f"split ratio must be positive, got {ratio}")
        return price / ratio
