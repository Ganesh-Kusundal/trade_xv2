"""Deterministic same-bar signal coordination (ADR-0012 workstream 3)."""

from __future__ import annotations

from dataclasses import dataclass, field

from domain.models.trading import SignalDTO


@dataclass
class SignalCoordinator:
    """Collapse multiple same-bar intents to one net signal per symbol."""

    _pending: dict[tuple[str, object], SignalDTO] = field(default_factory=dict)

    def submit(self, signal: SignalDTO, *, bar_key: object) -> SignalDTO | None:
        """Register *signal* for (*symbol*, *bar_key*); return winner if replaced."""
        key = (signal.symbol, bar_key)
        existing = self._pending.get(key)
        if existing is None:
            self._pending[key] = signal
            return signal
        winner = _pick_winner(existing, signal)
        self._pending[key] = winner
        return winner if winner is not signal else None

    def flush(self, *, bar_key: object) -> list[SignalDTO]:
        """Return and clear all signals for *bar_key*."""
        out: list[SignalDTO] = []
        for (symbol, bk), sig in list(self._pending.items()):
            if bk == bar_key:
                out.append(sig)
                del self._pending[(symbol, bk)]
        return out

    def clear(self) -> None:
        self._pending.clear()


def _pick_winner(a: SignalDTO, b: SignalDTO) -> SignalDTO:
    """Higher confidence wins; tie-break by strategy name for determinism."""
    if float(b.confidence) > float(a.confidence):
        return b
    if float(b.confidence) < float(a.confidence):
        return a
    return b if (b.strategy or "") >= (a.strategy or "") else a


def coalesce_strategy_signals(signals: list) -> list:
    """Collapse multiple actionable signals on the same bar to one per symbol."""
    if len(signals) <= 1:
        return signals
    non_actionable: list = []
    winners: dict[str, object] = {}
    for signal in signals:
        if not getattr(signal, "is_actionable", False):
            non_actionable.append(signal)
            continue
        sym = signal.symbol
        existing = winners.get(sym)
        if existing is None:
            winners[sym] = signal
            continue
        if float(signal.confidence) > float(existing.confidence):
            winners[sym] = signal
        elif float(signal.confidence) == float(existing.confidence):
            if (signal.strategy or "") >= (existing.strategy or ""):
                winners[sym] = signal
    return non_actionable + list(winners.values())


__all__ = ["SignalCoordinator", "coalesce_strategy_signals"]
