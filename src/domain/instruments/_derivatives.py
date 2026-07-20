"""Derivative instrument types (Future, Commodity, Option)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

from domain.candles.historical import HistoricalSeries, InstrumentRef
from domain.constants.market import DEFAULT_TICK_SIZE
from domain.instruments.instrument import Instrument
from domain.instruments.instrument_id import InstrumentId


class Future(Instrument):
    """Futures instrument. ``Future("NIFTY", expiry=date(...))``."""

    def __init__(
        self,
        symbol: str,
        exchange: str = "NFO",
        *,
        expiry: date,
        kind: str | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(
            InstrumentId.future(exchange, symbol, expiry, kind=kind),
            **kwargs,
        )
        self._expiry = expiry

    @property
    def expiry(self) -> date:
        return self._expiry

    def _futures_ltp(self) -> Decimal | None:
        if self.ltp is not None:
            return self.ltp
        try:
            q = self.refresh()
            return q.ltp if q is not None else None
        except Exception:
            return None

    def _spot_ltp(self, spot: Decimal | None = None) -> Decimal | None:
        if spot is not None:
            return spot
        from domain.instruments.derivatives_math import map_underlying_cash_exchange

        try:
            provider = self._resolve_provider()
        except Exception:
            return None
        cash_ex = map_underlying_cash_exchange(self.exchange)
        und_id = InstrumentId.equity(cash_ex, self.symbol)
        q = provider.get_quote(und_id)
        if q is None:
            und_id = InstrumentId.index(cash_ex, self.symbol)
            q = provider.get_quote(und_id)
        return q.ltp if q is not None else None

    def basis(self, spot: Decimal | None = None) -> Decimal | None:
        """F - S (normative). None if either leg missing."""
        from domain.instruments.derivatives_math import future_basis

        return future_basis(self._futures_ltp(), self._spot_ltp(spot))

    def cost_of_carry(self, rate: Decimal | None = None) -> Decimal | None:
        """Implied continuous rate if rate is None; else F - S*e^{rT}."""
        from domain.instruments.derivatives_math import cost_of_carry_basis, year_fraction

        return cost_of_carry_basis(
            self._futures_ltp(),
            self._spot_ltp(),
            year_fraction(self._expiry),
            rate,
        )

    def continuous(self) -> HistoricalSeries:
        """v1: empty DERIVED continuous series (no provider continuous support)."""
        return HistoricalSeries(
            bars=[],
            coverage=None,
            instrument=InstrumentRef(symbol=self.symbol, exchange=self.exchange),
            timeframe="1D",
            merge_manifest=None,
        )


class Commodity(Future):
    """Commodity future (typically MCX)."""

    def __init__(
        self,
        symbol: str,
        exchange: str = "MCX",
        *,
        expiry: date,
        **kwargs: Any,
    ) -> None:
        Future.__init__(self, symbol, exchange, expiry=expiry, kind="COMMODITY", **kwargs)

    @property
    def expiry(self) -> date:
        return self._expiry

    def _spot_ltp(self, spot: Decimal | None = None) -> Decimal | None:
        if spot is not None:
            return spot
        from domain.instruments.derivatives_math import map_underlying_cash_exchange

        try:
            provider = self._resolve_provider()
        except Exception:
            return None
        cash_ex = map_underlying_cash_exchange(self.exchange)
        und_id = InstrumentId.equity(cash_ex, self.symbol)
        q = provider.get_quote(und_id)
        if q is None:
            und_id = InstrumentId.index(cash_ex, self.symbol)
            q = provider.get_quote(und_id)
        return q.ltp if q is not None else None

    def _futures_ltp(self) -> Decimal | None:
        if self.ltp is not None:
            return self.ltp
        try:
            q = self.refresh()
            return q.ltp if q is not None else None
        except Exception:
            return None

    def basis(self, spot: Decimal | None = None) -> Decimal | None:
        """F - S (normative). None if either leg missing."""
        from domain.instruments.derivatives_math import future_basis

        return future_basis(self._futures_ltp(), self._spot_ltp(spot))

    def cost_of_carry(self, rate: Decimal | None = None) -> Decimal | None:
        """Implied continuous rate if rate is None; else F - S*e^{rT}."""
        from domain.instruments.derivatives_math import cost_of_carry_basis, year_fraction

        return cost_of_carry_basis(
            self._futures_ltp(),
            self._spot_ltp(),
            year_fraction(self._expiry),
            rate,
        )

    def rollover(self) -> Future | None:
        """Next expiry Future on same underlying; stamps same ports."""
        try:
            provider = self._resolve_provider()
        except Exception:
            return None
        try:
            chain = provider.get_future_chain(self._id)
        except Exception:
            return None
        contracts = getattr(chain, "contracts", None) or getattr(chain, "futures", None) or []
        next_exp: date | None = None
        for c in contracts:
            exp = getattr(c, "expiry", None)
            if isinstance(exp, str):
                for fmt in ("%Y-%m-%d", "%Y%m%d"):
                    try:
                        from datetime import datetime as _dt

                        exp = _dt.strptime(exp, fmt).date()
                        break
                    except ValueError:
                        continue
            if isinstance(exp, date) and exp > self._expiry:
                if next_exp is None or exp < next_exp:
                    next_exp = exp
        if next_exp is None:
            return None
        fut = Future(
            self.symbol,
            self.exchange,
            expiry=next_exp,
            data_provider=self._provider,
            execution_provider=self._executor,
        )
        osvc = self._resolve_order_service()
        if osvc is not None or self._provider is not None:
            fut._bind_session_ports(
                data_provider=self._provider,
                execution_provider=self._executor,
                order_service=osvc,
            )
        return fut

    def continuous(self) -> HistoricalSeries:
        """v1: empty DERIVED continuous series (no provider continuous support)."""
        return HistoricalSeries(
            bars=[],
            coverage=None,
            instrument=InstrumentRef(symbol=self.symbol, exchange=self.exchange),
            timeframe="1D",
            merge_manifest=None,
        )


class Option(Instrument):
    """Option instrument. Usually built from a chain leg."""

    def __init__(
        self,
        instrument_id: InstrumentId,
        *,
        strike: Decimal,
        expiry: date | None,
        right: str,
        leg: Any | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(instrument_id, **kwargs)
        self._strike = Decimal(str(strike))
        self._expiry = expiry
        self._right = right
        self._leg = leg

    @property
    def strike(self) -> Decimal:
        return self._strike

    @property
    def expiry(self) -> date | None:
        return self._expiry

    @property
    def right(self) -> str:
        return self._right

    @property
    def is_call(self) -> bool:
        return self._right == "CE"

    @property
    def is_put(self) -> bool:
        return self._right == "PE"

    @property
    def greeks(self):
        from domain.options.greeks import Greeks

        leg_greeks = getattr(self._leg, "greeks", None)
        return Greeks.from_dict(leg_greeks) if leg_greeks else Greeks.zero()

    @property
    def iv(self):
        return getattr(self._leg, "iv", None)

    @property
    def delta(self) -> Decimal:
        return self.greeks.delta

    def black_scholes(
        self,
        spot: Decimal,
        rate: Decimal | None = None,
        vol: Decimal | None = None,
        *,
        t: Decimal | None = None,
        dividend_yield: Decimal | None = None,
    ) -> Decimal | None:
        from domain.instruments.derivatives_math import black_scholes_price, year_fraction

        sigma = vol if vol is not None else self.iv
        if sigma is None:
            return None
        if not isinstance(sigma, Decimal):
            sigma = Decimal(str(sigma))
        tau = t if t is not None else year_fraction(self._expiry)
        if tau is None:
            return None
        r = rate if rate is not None else Decimal("0")
        q = dividend_yield if dividend_yield is not None else Decimal("0")
        return black_scholes_price(
            Decimal(str(spot)),
            self._strike,
            tau,
            r,
            sigma,
            is_call=self.is_call,
            dividend_yield=q,
        )

    def payoff(self, spot: Decimal) -> Decimal:
        from domain.instruments.derivatives_math import option_payoff

        return option_payoff(Decimal(str(spot)), self._strike, is_call=self.is_call)

    def intrinsic_value(self, spot: Decimal) -> Decimal:
        return self.payoff(spot)

    def extrinsic_value(self, spot: Decimal) -> Decimal | None:
        mkt = self.ltp
        if mkt is None and self._leg is not None:
            mkt = getattr(self._leg, "ltp", None)
        if mkt is None:
            return None
        return Decimal(str(mkt)) - self.intrinsic_value(spot)

    def moneyness(self, spot: Decimal) -> str:
        from domain.instruments.derivatives_math import moneyness_label

        return moneyness_label(
            Decimal(str(spot)),
            self._strike,
            is_call=self.is_call,
            tick_size=self.tick_size or DEFAULT_TICK_SIZE,
        )

    def implied_volatility(
        self,
        market_price: Decimal,
        spot: Decimal | None = None,
        rate: Decimal | None = None,
        *,
        t: Decimal | None = None,
    ) -> Decimal | None:
        from domain.instruments.derivatives_math import implied_volatility, year_fraction

        s = spot
        if s is None:
            s = self.ltp
        if s is None:
            return None
        tau = t if t is not None else year_fraction(self._expiry)
        if tau is None or tau <= 0:
            return None
        r = rate if rate is not None else Decimal("0")
        return implied_volatility(
            Decimal(str(market_price)),
            Decimal(str(s)),
            self._strike,
            tau,
            r,
            is_call=self.is_call,
        )

    @classmethod
    def from_leg(
        cls,
        underlying: str,
        exchange: str,
        expiry: date | str | None,
        strike: Decimal,
        right: str,
        leg: Any,
        **kwargs: Any,
    ) -> Option:
        order_service = kwargs.pop("order_service", None)
        if isinstance(expiry, str):
            from datetime import datetime

            for fmt in ("%Y-%m-%d", "%Y%m%d"):
                try:
                    expiry = datetime.strptime(expiry, fmt).date()
                    break
                except ValueError:
                    continue
        iid = InstrumentId.option(exchange, underlying, expiry, strike, right)
        opt = cls(iid, strike=strike, expiry=expiry, right=right, leg=leg, **kwargs)
        if order_service is not None:
            opt._bind_session_ports(
                data_provider=kwargs.get("data_provider"),
                execution_provider=kwargs.get("execution_provider"),
                order_service=order_service,
            )
        return opt
