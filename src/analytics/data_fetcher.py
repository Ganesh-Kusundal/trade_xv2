"""Data fetching for the Analytics facade.

Extracts the historical-data and option-chain fetch helpers from
:class:`~analytics.facade.Analytics`. These methods need a market-data
``provider`` (and, for the ``Instrument`` fast paths, the instrument
and its analyzer) and return :class:`~analytics.core.models.AnalysisResult`
objects.

This module is a leaf: it must not import from ``analytics.facade`` (circular
import guard).
"""

from __future__ import annotations

import logging

import pandas as pd

from analytics.core.instrument_analyzer import InstrumentAnalyzer
from analytics.core.models import AnalysisResult
from analytics.core.providers import MarketDataProvider
from analytics.engine_factory import AnalyticsEngineFactory
from domain.instruments.instrument import Instrument

logger = logging.getLogger(__name__)


class AnalyticsDataFetcher:
    """Fetches historical data and option chains into AnalysisResult objects.

    Dependencies are injected via the constructor so the class is usable
    without a fully-constructed facade.
    """

    def __init__(
        self,
        provider: MarketDataProvider | None = None,
        instrument: Instrument | None = None,
        instrument_analyzer: InstrumentAnalyzer | None = None,
        engines: AnalyticsEngineFactory | None = None,
    ) -> None:
        self.provider = provider
        self._instrument = instrument
        self._instrument_analyzer = instrument_analyzer
        self._engines = engines or AnalyticsEngineFactory(provider=provider)

    def fetch_history(
        self,
        symbol: str | Instrument | None = None,
        *,
        timeframe: str = "1D",
        lookback_days: int = 120,
        from_date: str | None = None,
        to_date: str | None = None,
    ) -> AnalysisResult:
        """Fetch historical data for a symbol or Instrument.

        When an Instrument is passed, delegates to its own
        get_history() method — no provider needed.
        When no symbol is provided, uses the instrument set at construction.
        """
        if symbol is None:
            if self._instrument is not None:
                symbol = self._instrument
            else:
                return AnalysisResult(
                    name="history",
                    symbol="unknown",
                    summary="No symbol provided and no instrument set.",
                )
        if isinstance(symbol, Instrument):
            instrument = symbol
            data = instrument.get_history(
                timeframe=timeframe,
                lookback_days=lookback_days,
            )
            sym = instrument.symbol
        else:
            sym = symbol
            if self.provider is None:
                return AnalysisResult(
                    name="history", symbol=sym, summary="No market-data provider configured."
                )
            data = self.provider.history(
                sym,
                timeframe=timeframe,
                lookback_days=lookback_days,
                from_date=from_date,
                to_date=to_date,
            )
        return AnalysisResult(
            name="history",
            symbol=sym,
            summary=f"Fetched {len(data)} bars for {sym}.",
            metrics={"bars": len(data), "columns": list(data.columns)},
            charts=[{"type": "history", "data": data.to_dict("records")[:1000]}],
        )

    def fetch_option_chain(
        self,
        underlying: str | Instrument | None = None,
        *,
        expiry: str | None = None,
    ) -> AnalysisResult:
        """Fetch option chain for a symbol or Instrument.

        When no symbol is provided, uses the instrument set at construction.
        """
        if underlying is None:
            underlying = self._instrument
        if underlying is None:
            return AnalysisResult(
                name="option_chain", symbol="unknown", summary="No symbol provided."
            )
        if isinstance(underlying, Instrument):
            instrument = underlying
            chain = instrument.get_option_chain()
            sym = instrument.symbol
            strikes = chain.strikes if chain else []
        else:
            sym = underlying
            if self.provider is None:
                return AnalysisResult(
                    name="option_chain",
                    symbol=sym,
                    summary="No market-data provider configured.",
                )
            chain = self.provider.option_chain(sym, expiry=expiry)
            strikes = chain.get("strikes", []) if isinstance(chain, dict) else []
        return AnalysisResult(
            name="option_chain",
            symbol=sym,
            summary=f"Fetched {len(strikes)} option-chain strikes for {sym}.",
            metrics={
                "strikes": len(strikes),
                "underlying": sym,
                "expiry": expiry,
            },
            charts=[{"type": "option_chain", "data": strikes}],
        )

    def stock(
        self,
        symbol: str | Instrument | None = None,
        prices: pd.DataFrame | None = None,
        benchmark_prices: pd.DataFrame | None = None,
        benchmark_symbol: str = "NIFTY",
        sector_prices: pd.DataFrame | None = None,
    ) -> AnalysisResult:
        """Analyze a stock by symbol or Instrument.

        When an Instrument is passed (and prices is None),
        delegates to InstrumentAnalyzer.
        When no symbol is provided, uses the instrument set at construction.
        """
        if symbol is None:
            symbol = self._instrument
        if symbol is None:
            return AnalysisResult(name="stock", symbol="unknown", summary="No symbol provided.")
        if isinstance(symbol, Instrument):
            instrument = symbol
            if self._instrument_analyzer is not None:
                return self._instrument_analyzer.analyze_stock(
                    instrument,
                    lookback_days=120,
                )
            prices = instrument.get_history()
            sym = instrument.symbol
        else:
            sym = symbol
        if prices is None or prices.empty:
            return AnalysisResult(name="stock", symbol=sym, summary=f"No data available for {sym}.")
        logger.info("Analyzing stock %s (%d bars)", sym, len(prices))
        return self._engines.stock_engine.analyze(
            sym, prices, benchmark_prices, benchmark_symbol, sector_prices
        )

    def future(
        self,
        symbol: str,
        *,
        spot_price: float | None = None,
        future_price: float | None = None,
        current_oi: float | None = None,
        next_oi: float | None = None,
        price_change: float = 0.0,
        oi_change: float = 0.0,
    ) -> AnalysisResult:
        logger.info("Analyzing future %s (spot=%s, future=%s)", symbol, spot_price, future_price)
        return self._engines.future_engine.analyze(
            symbol,
            spot_price=spot_price,
            future_price=future_price,
            current_oi=current_oi,
            next_oi=next_oi,
            price_change=price_change,
            oi_change=oi_change,
        )

    def options(
        self,
        underlying: str | Instrument | None = None,
        chain: pd.DataFrame | dict | None = None,
        *,
        spot_price: float | None = None,
        iv_history: list[float] | pd.Series | None = None,
    ) -> AnalysisResult:
        """Analyze options by symbol or Instrument.

        When an Instrument is passed (and chain is None),
        delegates to InstrumentAnalyzer.
        When no symbol is provided, uses the instrument set at construction.
        """
        if underlying is None:
            underlying = self._instrument
        if underlying is None:
            return AnalysisResult(name="options", symbol="unknown", summary="No symbol provided.")
        if isinstance(underlying, Instrument):
            instrument = underlying
            if self._instrument_analyzer is not None:
                return self._instrument_analyzer.analyze_options(
                    instrument,
                    spot_price=spot_price,
                )
            chain_obj = instrument.get_option_chain()
            chain = chain_obj.to_dict() if chain_obj and chain_obj.strikes else {}
            sym = instrument.symbol
        else:
            sym = underlying
        if chain is None:
            return AnalysisResult(
                name="options", symbol=sym, summary=f"No option chain available for {sym}."
            )
        chain_len = (
            len(chain)
            if isinstance(chain, pd.DataFrame)
            else len(chain.get("strikes", []))
            if isinstance(chain, dict)
            else 0
        )
        logger.info("Analyzing options %s (%d strikes)", sym, chain_len)
        return self._engines.options_engine.analyze(
            sym, chain, spot_price=spot_price, iv_history=iv_history
        )

    def volatility(
        self,
        symbol: str | Instrument | None = None,
        prices: pd.DataFrame | None = None,
        *,
        implied_volatility: float | None = None,
        iv_history: list[float] | pd.Series | None = None,
    ) -> AnalysisResult:
        """Analyze volatility by symbol or Instrument.

        When an Instrument is passed (and prices is None),
        delegates to InstrumentAnalyzer.
        When no symbol is provided, uses the instrument set at construction.
        """
        if symbol is None:
            symbol = self._instrument
        if symbol is None:
            return AnalysisResult(
                name="volatility", symbol="unknown", summary="No symbol provided."
            )
        if isinstance(symbol, Instrument):
            instrument = symbol
            if self._instrument_analyzer is not None:
                return self._instrument_analyzer.analyze_volatility(
                    instrument,
                    implied_volatility=implied_volatility,
                )
            prices = instrument.get_history()
            sym = instrument.symbol
        else:
            sym = symbol
        if prices is None or prices.empty:
            return AnalysisResult(
                name="volatility", symbol=sym, summary=f"No data available for {sym}."
            )
        logger.info("Analyzing volatility %s (%d bars)", sym, len(prices))
        return self._engines.volatility_engine.analyze(
            sym, prices, implied_volatility=implied_volatility, iv_history=iv_history
        )
