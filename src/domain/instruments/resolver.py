"""Instrument name resolver + light doctor (UX-3).

Uses display-name parse and optional fuzzy match against a symbol list.
No broker/gateway imports.
"""

from __future__ import annotations

from difflib import get_close_matches
from typing import Iterable, Sequence

from domain.instruments.display_names import format_display_name, parse_display_name
from domain.instruments.instrument_id import InstrumentId


class InstrumentResolver:
    """Resolve display / canonical names to :class:`InstrumentId`."""

    def __init__(
        self,
        *,
        known_symbols: Sequence[str] | None = None,
        default_exchange: str = "NSE",
    ) -> None:
        self._known = [s.upper() for s in (known_symbols or ())]
        self._default_exchange = default_exchange

    def resolve(
        self,
        name: str,
        *,
        default_exchange: str | None = None,
        default_year: int | None = None,
    ) -> InstrumentId:
        """Exact parse; on bare-symbol failure try fuzzy known list."""
        exch = default_exchange or self._default_exchange
        raw = " ".join(str(name).strip().split())
        # Prefer fuzzy when bare token looks like a typo of a known symbol
        token = raw.upper()
        if self._known and " " not in token and ":" not in token:
            matches = get_close_matches(token, self._known, n=1, cutoff=0.8)
            if matches and matches[0] != token:
                return parse_display_name(
                    matches[0], default_exchange=exch, default_year=default_year
                )
        try:
            return parse_display_name(
                name, default_exchange=exch, default_year=default_year
            )
        except ValueError:
            if self._known and token:
                matches = get_close_matches(token, self._known, n=1, cutoff=0.6)
                if matches:
                    return parse_display_name(
                        matches[0], default_exchange=exch, default_year=default_year
                    )
            raise ValueError(f"Cannot resolve instrument name: {name!r}")

    def suggest(self, name: str, *, n: int = 5) -> list[str]:
        raw = " ".join(str(name).strip().split()).upper()
        if not self._known or not raw:
            return []
        return get_close_matches(raw, self._known, n=n, cutoff=0.5)

    def doctor(self, name: str) -> dict:
        """Diagnostic dict: parse ok, canonical, display, suggestions."""
        out: dict = {
            "input": name,
            "ok": False,
            "canonical": None,
            "display": None,
            "error": None,
            "suggestions": self.suggest(name),
        }
        try:
            iid = self.resolve(name)
            out["ok"] = True
            out["canonical"] = str(iid)
            out["display"] = format_display_name(iid)
            out["asset_type"] = iid.asset_type
            out["exchange"] = iid.exchange
        except Exception as exc:
            out["error"] = str(exc)
        return out

    def extend_symbols(self, symbols: Iterable[str]) -> None:
        for s in symbols:
            u = str(s).upper()
            if u and u not in self._known:
                self._known.append(u)
