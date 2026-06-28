"""Scanner framework — Protocol, Candidate, and ScanResult models.

Usage:
    scanner = MomentumScanner(pipeline)
    result = scanner.scan(universe_df)
    for candidate in result.candidates:
        print(candidate.symbol, candidate.score)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from enum import Enum
from typing import Any, Protocol, runtime_checkable

import pandas as pd

from analytics.pipeline.pipeline import FeaturePipeline

# ---------------------------------------------------------------------------
# Scanner State (P2-Phase 2)
# ---------------------------------------------------------------------------


class ScannerState(str, Enum):
    """Scanner lifecycle states.

    Transitions:
    - IDLE → RUNNING (start scan)
    - RUNNING → COMPLETED (scan finished successfully)
    - RUNNING → FAILED (scan failed with error)
    - COMPLETED → IDLE (ready for next scan)
    - FAILED → IDLE (retry after failure)
    """

    IDLE = "IDLE"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"

    @property
    def is_active(self) -> bool:
        """True if scanner is currently running."""
        return self == ScannerState.RUNNING

    @property
    def is_terminal(self) -> bool:
        """True if scanner has completed or failed."""
        return self in (ScannerState.COMPLETED, ScannerState.FAILED)


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Candidate:
    """A stock selected by a scanner with a score and reasons."""

    symbol: str
    score: Decimal
    reasons: list[str] = field(default_factory=list)
    metrics: dict[str, Decimal] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not Decimal("0") <= self.score <= Decimal("100"):
            raise ValueError(f"Score must be 0-100, got {self.score}")


@dataclass
class ScanResult:
    """Output of a scanner run."""

    scanner: str
    candidates: list[Candidate] = field(default_factory=list)
    universe_size: int = 0
    metrics: dict[str, Decimal] = field(default_factory=dict)

    @property
    def count(self) -> int:
        return len(self.candidates)

    def top(self, n: int = 10) -> list[Candidate]:
        return sorted(self.candidates, key=lambda c: (-c.score, c.symbol))[:n]

    def to_dataframe(self) -> pd.DataFrame:
        if not self.candidates:
            return pd.DataFrame(columns=["symbol", "score", "reasons"])
        rows = [
            {
                "symbol": c.symbol,
                "score": c.score,
                "reasons": ", ".join(c.reasons),
                **c.metrics,
            }
            for c in self.candidates
        ]
        return pd.DataFrame(rows).sort_values("score", ascending=False).reset_index(drop=True)


# ---------------------------------------------------------------------------
# Scanner Protocol
# ---------------------------------------------------------------------------


@runtime_checkable
class Scanner(Protocol):
    """Protocol for all scanners.

    A scanner receives a universe DataFrame (multiple symbols)
    and returns a ScanResult with ranked candidates.
    """

    name: str

    def scan(self, universe: pd.DataFrame) -> ScanResult: ...


# ---------------------------------------------------------------------------
# Base scanner with shared logic
# ---------------------------------------------------------------------------


@dataclass
class BaseScanner:
    """Base class for scanners that use FeaturePipeline.

    P1-Phase 1: Added optional event_bus parameter for publishing
    SCAN_STARTED, CANDIDATE_GENERATED, and SCAN_COMPLETED events.

    P5.1: Optimized _compute_features to avoid unnecessary DataFrame copy
    when pipeline already returns an isolated DataFrame.
    """

    pipeline: FeaturePipeline
    name: str = "base"
    top_n: int = 10
    event_bus: Any | None = None
    _candidates: list[Candidate] = field(default_factory=list, init=False, repr=False)

    def scan(self, universe: pd.DataFrame) -> ScanResult:
        """Default scan: compute features, score, rank. Override for custom logic.

        P1-Phase 1: Publishes SCAN_STARTED and SCAN_COMPLETED events.
        """
        if self.event_bus is not None:
            from domain.events import EventType

            self.event_bus.publish(
                EventType.SCAN_STARTED.value,
                payload={
                    "profile": self.name,
                    "universe": len(universe),
                },
            )

        raise NotImplementedError("Subclasses must implement scan()")

    def _compute_features(self, universe: pd.DataFrame) -> pd.DataFrame:
        """Run the pipeline on the entire universe.

        P5.1: Avoid unnecessary .copy() — pipeline.run() already returns
        a new DataFrame, so we can safely mutate it in-place downstream.
        """
        df = universe
        # Ensure symbol column exists — use index as symbol if missing
        if "symbol" not in df.columns:
            df = df.copy()  # Must copy before adding column
            df["symbol"] = df.index.astype(str)
        # Ensure required OHLCV columns have defaults
        for col in ("open", "high", "low", "close", "volume"):
            if col not in df.columns:
                if col == "volume":
                    df = df.copy() if df is universe else df
                    df[col] = 0
                else:
                    df = df.copy() if df is universe else df
                    df[col] = df.get("close", 0.0)
        # Ensure timestamp column exists
        if "timestamp" not in df.columns:
            df = df.copy() if df is universe else df
            df["timestamp"] = pd.Timestamp.now()
        return self.pipeline.run(df)

    def _score_candidates(self, scored: pd.DataFrame) -> ScanResult:
        """Convert scored DataFrame into ScanResult (vectorized data extraction)."""
        signal_cols = [col for col in scored.columns if col.endswith("_signal")]

        def _to_decimal(val: object, default: str = "50") -> Decimal:
            if val is None or (isinstance(val, float) and pd.isna(val)):
                return Decimal(default)
            return Decimal(str(round(float(val), 8)))

        for row in scored.itertuples(index=False):
            reasons = [str(getattr(row, col)) for col in signal_cols if getattr(row, col, None)]
            score_val = getattr(row, "composite_score", 50.0)

            score_metric_cols = [col for col in scored.columns if col.startswith("score_")]
            metrics = {
                col: _to_decimal(getattr(row, col, None))
                for col in score_metric_cols
                if not pd.isna(getattr(row, col, None))
            }

            candidate = Candidate(
                symbol=str(getattr(row, "symbol", "UNKNOWN")),
                score=_to_decimal(score_val),
                reasons=reasons,
                metrics=metrics,
            )
            self._candidates.append(candidate)

            if self.event_bus is not None:
                from domain.events import EventType

                self.event_bus.publish(
                    EventType.CANDIDATE_GENERATED.value,
                    payload={
                        "symbol": candidate.symbol,
                        "score": candidate.score,
                        "reason": ", ".join(candidate.reasons),
                    },
                )

        result = ScanResult(
            scanner=self.name,
            candidates=self._candidates,
            universe_size=len(scored),
        )

        if self.event_bus is not None:
            from domain.events import EventType

            self.event_bus.publish(
                EventType.SCAN_COMPLETED.value,
                payload={
                    "candidate_count": len(self._candidates),
                    "universe": len(scored),
                },
            )

        self._candidates = []
        return result
