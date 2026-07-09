"""Instrument composition helpers — identity, trading spec, extensions.

Extracted from the Instrument aggregate so the public object stays thin.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from domain.instruments.instrument_id import InstrumentId


@dataclass(frozen=True, slots=True)
class InstrumentIdentity:
    """Static identity for an instrument."""

    instrument_id: InstrumentId

    @property
    def symbol(self) -> str:
        return self.instrument_id.underlying

    @property
    def exchange(self) -> str:
        return self.instrument_id.exchange

    @property
    def asset_type(self) -> str:
        return self.instrument_id.asset_type


@dataclass(frozen=True, slots=True)
class TradingSpec:
    """Trading constraints / sizing metadata."""

    lot_size: int = 1
    tick_size: Decimal = Decimal("0.05")
    product_types: tuple[str, ...] = ()
    margin_required: Decimal | None = None

    @classmethod
    def from_metadata(cls, metadata: dict[str, Any]) -> TradingSpec:
        raw_tick = metadata.get("tick_size")
        return cls(
            lot_size=int(metadata.get("lot_size", 1) or 1),
            tick_size=Decimal(str(raw_tick)) if raw_tick is not None else Decimal("0.05"),
            product_types=tuple(metadata.get("product_types") or ()),
            margin_required=(
                Decimal(str(metadata["margin_required"]))
                if metadata.get("margin_required") is not None
                else None
            ),
        )


@dataclass
class ExtensionManager:
    """Named extension registry attached to an Instrument."""

    _extensions: dict[str, Any] = field(default_factory=dict)

    def get(self, name: str) -> Any | None:
        return self._extensions.get(name)

    def register(self, name: str, extension: Any) -> None:
        self._extensions[name] = extension

    def list(self) -> list[str]:
        return sorted(self._extensions)

    def values(self) -> list[Any]:
        return list(self._extensions.values())

    def __contains__(self, name: str) -> bool:
        return name in self._extensions
