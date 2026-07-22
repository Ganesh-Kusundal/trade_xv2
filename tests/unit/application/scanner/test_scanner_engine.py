"""Unit tests for ScannerEngine candidate screening and deterministic hashing."""

from decimal import Decimal
import pytest
from application.scanner.scanner_engine import ScannerCandidate, ScannerEngine


def test_scanner_candidate_deterministic_hash():
    c1 = ScannerCandidate(
        symbol="RELIANCE",
        exchange="NSE",
        score=Decimal("0.85"),
        signal_type="BULLISH_BREAKOUT",
        metadata={"rsi": 68.5},
    )
    c2 = ScannerCandidate(
        symbol="RELIANCE",
        exchange="NSE",
        score=Decimal("0.85"),
        signal_type="BULLISH_BREAKOUT",
        metadata={"rsi": 68.5},
    )

    # Identical candidate attributes must yield identical candidate_id
    assert c1.candidate_id == c2.candidate_id
    assert c1.candidate_id.startswith("cand_")


def test_scanner_engine_runs_screening_rule():
    engine = ScannerEngine()

    def rsi_screener(quote_data: dict) -> ScannerCandidate | None:
        if quote_data.get("rsi", 0) > 70:
            return ScannerCandidate(
                symbol=quote_data["symbol"],
                exchange=quote_data["exchange"],
                score=Decimal(str(quote_data["rsi"] / 100.0)),
                signal_type="OVERBOUGHT",
            )
        return None

    engine.add_screener(rsi_screener)

    quotes = [
        {"symbol": "TCS", "exchange": "NSE", "rsi": 62.0},
        {"symbol": "INFY", "exchange": "NSE", "rsi": 75.4},
    ]

    candidates = engine.scan(quotes)
    assert len(candidates) == 1
    assert candidates[0].symbol == "INFY"
    assert candidates[0].signal_type == "OVERBOUGHT"
