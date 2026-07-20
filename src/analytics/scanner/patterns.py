"""Candlestick pattern engine + registry for the scanner/strategy runner.

Mirrors :mod:`analytics.strategy.registry` (``PatternRegistry``) and
:mod:`analytics.scanner.scanners` (``BaseScanner`` / ``MomentumScanner``). The
engine wraps the pure domain detector from
:mod:`domain.indicators.patterns` and emits a :class:`PatternResult` (frozen,
mirroring ``ScanResult``) of :class:`PatternHit` rows.

A :class:`PatternScanner` and :class:`PatternStrategy` let patterns drive
scanner ranking and strategy signals respectively, reusing the existing
``FeaturePipeline`` + ``StrategyPipeline`` machinery for parity.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from decimal import Decimal
from typing import ClassVar

import pandas as pd

from analytics.pipeline.pipeline import FeaturePipeline
from analytics.scanner.models import BaseScanner, ScanResult
from analytics.strategy.models import Signal, SignalType
from analytics.strategy.registry import StrategyRegistry
from domain.indicators.patterns import PatternColumns

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Pattern direction mapping
# ---------------------------------------------------------------------------

_BULLISH_PATTERNS = {
    PatternColumns.ENGULFING_BULL,
    PatternColumns.HAMMER,
    PatternColumns.HARAMI_BULL,
    PatternColumns.SWING_CONTINUATION,
}
_BEARISH_PATTERNS = {
    PatternColumns.ENGULFING_BEAR,
    PatternColumns.SHOOTING_STAR,
    PatternColumns.HARAMI_BEAR,
    PatternColumns.SWING_BREAKDOWN,
}
_FLAG_COLUMNS = [c for c in PatternColumns.ALL if c != PatternColumns.DIRECTION]


def _pattern_direction(column: str) -> str:
    if column in _BULLISH_PATTERNS:
        return "BULL"
    if column in _BEARISH_PATTERNS:
        return "BEAR"
    return "NEUTRAL"


# ---------------------------------------------------------------------------
# Result models (mirror Candidate / ScanResult)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PatternHit:
    """A pattern detected on a symbol's latest bar."""

    symbol: str
    pattern: str
    direction: str  # BULL / BEAR / NEUTRAL
    strength: Decimal
    reasons: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class PatternResult:
    """Output of a :class:`PatternEngine` run."""

    engine: str
    hits: list[PatternHit] = field(default_factory=list)
    universe_size: int = 0

    @property
    def count(self) -> int:
        return len(self.hits)

    def to_dataframe(self) -> pd.DataFrame:
        if not self.hits:
            return pd.DataFrame(columns=["symbol", "pattern", "direction", "strength"])
        rows = [
            {
                "symbol": h.symbol,
                "pattern": h.pattern,
                "direction": h.direction,
                "strength": h.strength,
                "reasons": ", ".join(h.reasons),
            }
            for h in self.hits
        ]
        return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Pattern registry (mirror StrategyRegistry)
# ---------------------------------------------------------------------------


class PatternRegistry:
    """Central registry for pattern engines / detectors.

    Mirrors :class:`analytics.strategy.registry.StrategyRegistry`: a singleton
    keyed by canonical name enabling manual registration, discovery, and
    factory-style instantiation.
    """

    _registry: ClassVar[dict[str, type]] = {}

    @classmethod
    def register(cls, name: str, engine_class: type) -> None:
        if name in cls._registry:
            logger.warning("Pattern '%s' already registered, overwriting", name)
        cls._registry[name] = engine_class
        logger.info("Pattern registered: %s -> %s", name, engine_class.__name__)

    @classmethod
    def get(cls, name: str) -> type:
        if name not in cls._registry:
            raise KeyError(
                f"Pattern '{name}' not found. Available: {', '.join(cls._registry.keys())}"
            )
        return cls._registry[name]

    @classmethod
    def create(cls, name: str, **kwargs) -> PatternEngine:
        return cls.get(name)(**kwargs)

    @classmethod
    def list(cls) -> list[str]:
        return sorted(cls._registry.keys())

    @classmethod
    def discover(cls, package_path: str) -> int:
        import importlib
        import pkgutil

        before = len(cls._registry)
        try:
            package = importlib.import_module(package_path)
            if hasattr(package, "__path__"):
                for _imp, modname, _ispkg in pkgutil.iter_modules(package.__path__):
                    try:
                        importlib.import_module(f"{package_path}.{modname}")
                    except Exception as exc:
                        logger.warning("Failed to import pattern module %s: %s", modname, exc)
        except Exception as exc:
            logger.error("Failed to discover patterns in %s: %s", package_path, exc)
        return len(cls._registry) - before

    @classmethod
    def clear(cls) -> None:
        cls._registry.clear()


# ---------------------------------------------------------------------------
# Pattern pipeline builder
# ---------------------------------------------------------------------------


def _build_pattern_pipeline() -> FeaturePipeline:
    from analytics.pipeline import ATR, RSI, SMA, CandlestickPattern

    return (
        FeaturePipeline()
        .add(CandlestickPattern())
        .add(RSI(period=14))
        .add(ATR(period=14))
        .add(SMA(period=20))
    )


# ---------------------------------------------------------------------------
# Pattern engine
# ---------------------------------------------------------------------------


@dataclass
class PatternEngine:
    """Detect candlestick + swing patterns across a universe.

    Mirrors :class:`analytics.scanner.scanners.BaseScanner`: runs a
    ``FeaturePipeline`` (with ``CandlestickPattern``) over the full universe,
    then inspects each symbol's latest bar and emits a :class:`PatternResult`.
    """

    name: str = "candlestick"
    top_n: int = 50
    pipeline: FeaturePipeline = field(default_factory=_build_pattern_pipeline)

    def run(self, universe: pd.DataFrame) -> PatternResult:
        if universe.empty:
            return PatternResult(engine=self.name, universe_size=0)

        df = self.pipeline.run(universe)
        hits: list[PatternHit] = []

        if "symbol" in df.columns:
            latest = df.sort_values("timestamp").groupby("symbol").last()
            universe_size = latest.shape[0]
            for symbol, row in latest.iterrows():
                hits.extend(self._hits_for_row(str(symbol), row))
        else:
            universe_size = 1
            row = df.iloc[-1]
            sym = str(df.index[-1]) if df.index.name else "UNKNOWN"
            hits.extend(self._hits_for_row(sym, row))

        hits = sorted(hits, key=lambda h: (-float(h.strength), h.symbol, h.pattern))[: self.top_n]
        return PatternResult(engine=self.name, hits=hits, universe_size=universe_size)

    @staticmethod
    def _hits_for_row(symbol: str, row: pd.Series) -> list[PatternHit]:
        detected = [c for c in _FLAG_COLUMNS if bool(row.get(c, False))]
        if not detected:
            return []
        return [
            PatternHit(
                symbol=symbol,
                pattern=col,
                direction=_pattern_direction(col),
                strength=Decimal("0.6"),
                reasons=[col],
            )
            for col in detected
        ]


# ---------------------------------------------------------------------------
# Pattern scanner (mirror MomentumScanner)
# ---------------------------------------------------------------------------


@dataclass
class PatternScanner(BaseScanner):
    """Rank symbols by candlestick pattern conviction."""

    name: str = "pattern"
    top_n: int = 10
    pipeline: FeaturePipeline = field(default_factory=_build_pattern_pipeline)

    def scan(self, universe: pd.DataFrame) -> ScanResult:
        if universe.empty:
            return ScanResult(scanner=self.name, universe_size=0)

        df = self._compute_features(universe)
        if "symbol" in df.columns:
            df = (
                df.sort_values("timestamp")
                .drop_duplicates(["symbol", "timestamp"], keep="last")
                .groupby("symbol")
                .last()
                .reset_index()
            )

        scored = self._score(df)
        scored = scored.sort_values(
            ["composite_score", "symbol"], ascending=[False, True], kind="mergesort"
        ).head(self.top_n)
        return self._score_candidates(scored)

    def _score(self, df: pd.DataFrame) -> pd.DataFrame:
        result = df
        bull = sum(
            result.get(c, pd.Series(False, index=result.index)).fillna(False).astype(int)
            for c in _BULLISH_PATTERNS
        )
        bear = sum(
            result.get(c, pd.Series(False, index=result.index)).fillna(False).astype(int)
            for c in _BEARISH_PATTERNS
        )
        result["score_bull"] = (50 + bull * 10).clip(0, 100)
        result["score_bear"] = (50 - bear * 10).clip(0, 100)
        result["composite_score"] = (50 + (bull - bear) * 10).clip(0, 100)

        # Vectorized signal column describing every detected pattern on the row
        def _detected_str(row: pd.Series) -> str:
            return ";".join(c for c in _FLAG_COLUMNS if bool(row.get(c, False)))

        result["pattern_signal"] = df.apply(_detected_str, axis=1).fillna("")
        return result


# ---------------------------------------------------------------------------
# Pattern strategy (mirror MomentumStrategy)
# ---------------------------------------------------------------------------


@dataclass
class PatternStrategy:
    """Strategy that emits BUY/SELL from candlestick pattern conviction."""

    name: str = "Pattern"

    def evaluate(self, candidate, features: pd.DataFrame) -> Signal:
        if features.empty:
            return Signal(
                symbol=candidate.symbol,
                signal_type=SignalType.HOLD,
                confidence=0.0,
                strategy=self.name,
                reasons=["No data"],
            )

        last = features.iloc[-1]
        bull = sum(1 for c in _BULLISH_PATTERNS if bool(last.get(c, False)))
        bear = sum(1 for c in _BEARISH_PATTERNS if bool(last.get(c, False)))
        close = float(last.get("close", 0.0))

        reasons: list[str] = []
        if bull > 0 and bull >= bear:
            signal_type = SignalType.BUY
            reasons.append(f"{bull} bullish pattern(s): {_detected(last, _BULLISH_PATTERNS)}")
            confidence = min(1.0, 0.5 + 0.1 * bull)
        elif bear > 0 and bear > bull:
            signal_type = SignalType.SELL
            reasons.append(f"{bear} bearish pattern(s): {_detected(last, _BEARISH_PATTERNS)}")
            confidence = min(1.0, 0.5 + 0.1 * bear)
        else:
            signal_type = SignalType.HOLD
            reasons.append("No actionable candlestick pattern")
            confidence = 0.0

        return Signal(
            symbol=candidate.symbol,
            signal_type=signal_type,
            confidence=round(confidence, 3),
            strategy=self.name,
            entry_price=close if close > 0 else None,
            reasons=reasons,
            metadata={"bull": bull, "bear": bear},
        )


def _detected(row: pd.Series, columns) -> str:
    return ", ".join(c for c in columns if bool(row.get(c, False)))


# ---------------------------------------------------------------------------
# Auto-registration (mirror analytics.strategy.builtins.halftrend)
# ---------------------------------------------------------------------------

PatternRegistry.register("candlestick", PatternEngine)
StrategyRegistry.register("pattern", PatternStrategy)
