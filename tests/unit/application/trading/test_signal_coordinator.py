"""Signal coalescing for same-bar multi-strategy intents."""

from __future__ import annotations

from dataclasses import dataclass

from application.trading.signal_coordinator import coalesce_strategy_signals


@dataclass
class _Sig:
    symbol: str
    confidence: float
    strategy: str
    is_actionable: bool = True


def test_coalesce_keeps_highest_confidence_per_symbol():
    signals = [
        _Sig("RELIANCE", 0.4, "momentum"),
        _Sig("RELIANCE", 0.9, "breakout"),
        _Sig("TCS", 0.5, "momentum"),
    ]
    out = coalesce_strategy_signals(signals)
    assert len(out) == 2
    by_sym = {s.symbol: s for s in out}
    assert by_sym["RELIANCE"].strategy == "breakout"
    assert by_sym["TCS"].strategy == "momentum"


def test_coalesce_preserves_non_actionable():
    signals = [
        _Sig("RELIANCE", 0.1, "watch", is_actionable=False),
        _Sig("RELIANCE", 0.9, "breakout"),
    ]
    out = coalesce_strategy_signals(signals)
    assert len(out) == 2
    assert any(not s.is_actionable for s in out)
