"""Scanner framework — Protocol, Candidate, and ScanResult models.

Usage:
    scanner = MomentumScanner(pipeline)
    result = scanner.scan(universe_df)
    for candidate in result.candidates:
        print(candidate.symbol, candidate.score)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

import pandas as pd

from analytics.pipeline.pipeline import FeaturePipeline

# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Candidate:
    """A stock selected by a scanner with a score and reasons."""

    symbol: str
    score: float
    reasons: list[str] = field(default_factory=list)
    metrics: dict[str, float] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not 0 <= self.score <= 100:
            raise ValueError(f"Score must be 0-100, got {self.score}")


@dataclass
class ScanResult:
    """Output of a scanner run."""

    scanner: str
    candidates: list[Candidate] = field(default_factory=list)
    universe_size: int = 0
    metrics: dict[str, float] = field(default_factory=dict)

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
    """Base class for scanners that use FeaturePipeline."""

    pipeline: FeaturePipeline
    name: str = "base"
    top_n: int = 10

    def scan(self, universe: pd.DataFrame) -> ScanResult:
        """Default scan: compute features, score, rank. Override for custom logic."""
        raise NotImplementedError("Subclasses must implement scan()")

    def _compute_features(self, universe: pd.DataFrame) -> pd.DataFrame:
        """Run the pipeline on the entire universe."""
        # Ensure symbol column exists — use index as symbol if missing
        df = universe.copy()
        if "symbol" not in df.columns:
            df["symbol"] = df.index.astype(str)
        # Ensure required OHLCV columns have defaults
        for col in ("open", "high", "low", "close", "volume"):
            if col not in df.columns:
                if col == "volume":
                    df[col] = 0
                else:
                    df[col] = df.get("close", 0.0)
        # Ensure timestamp column exists
        if "timestamp" not in df.columns:
            import pandas as pd
            df["timestamp"] = pd.Timestamp.now()
        return self.pipeline.run(df)

    def _score_candidates(self, scored: pd.DataFrame) -> ScanResult:
        """Convert scored DataFrame into ScanResult."""
        candidates = []
        for _, row in scored.iterrows():
            reasons = []
            for col in scored.columns:
                if col.endswith("_signal") and row.get(col):
                    reasons.append(str(row[col]))
            score_val = row.get("composite_score", 50.0)
            if pd.isna(score_val):
                score_val = 50.0
            candidates.append(
                Candidate(
                    symbol=str(row.get("symbol", "UNKNOWN")),
                    score=float(score_val),
                    reasons=reasons,
                    metrics={col: float(row[col]) for col in scored.columns if col.startswith("score_") and not pd.isna(row[col])},
                )
            )
        return ScanResult(
            scanner=self.name,
            candidates=candidates,
            universe_size=len(scored),
        )
