"""OptionChain — first-class aggregate, composed of Option instruments.

chain = nifty.option_chain()
chain.atm              # Option (call at the ATM strike)
chain.calls            # list[Option]
chain.puts             # list[Option]
chain.pcr()            # put/call open-interest ratio
chain.max_pain()       # max-pain strike
chain.itm()            # in-the-money options
chain.otm()            # out-of-the-money options
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING

from domain.candles.historical import DateRange, HistoricalSeries, InstrumentRef
from domain.entities.options import OptionChain as OptionChainVO
from domain.instruments.instrument_id import InstrumentId
from domain.options.greeks import Greeks
from domain.options.surfaces import GreeksSurface, IVSurface, VolatilitySurface

if TYPE_CHECKING:
    from domain.ports.protocols import DataProvider


class OptionChain:
    """Rich query surface over a normalized option-chain snapshot."""

    def __init__(
        self,
        chain: OptionChainVO,
        *,
        data_provider: DataProvider | None = None,
        provider: DataProvider | None = None,
    ) -> None:
        self._chain = chain
        # Accept both keyword spellings: ``data_provider`` (canonical port name)
        # and ``provider`` (used by call sites in ``instrument.py``).
        self._provider = data_provider or provider

    # ── Identity / state (read-through) ─────────────────────────────

    @property
    def underlying(self) -> str:
        return self._chain.underlying

    @property
    def exchange(self) -> str:
        return self._chain.exchange

    @property
    def expiry(self) -> str:
        return self._chain.expiry

    @property
    def expiries(self) -> tuple[str, ...]:
        return (self._chain.expiry,) if self._chain.expiry else ()

    @property
    def spot(self) -> Decimal | None:
        return self._chain.spot

    @property
    def strikes(self):
        return self._chain.strikes

    # ── Queries ─────────────────────────────────────────────────────

    def _atm_strike(self) -> Decimal | None:
        spot = self._chain.spot
        if spot is None or not self._chain.strikes:
            return None
        return min(
            (s.strike for s in self._chain.strikes),
            key=lambda k: abs(k - spot),
        )

    @property
    def atm(self):
        """The ATM call as a full Option instrument."""
        from domain.instruments.instrument import Option

        strike = self._atm_strike()
        if strike is None:
            return None
        row = next((s for s in self._chain.strikes if s.strike == strike), None)
        if row is None:
            return None
        return Option.from_leg(
            self._chain.underlying,
            self._chain.exchange,
            self._chain.expiry,
            strike,
            "CE",
            row.call,
            data_provider=self._provider,
        )

    @property
    def calls(self):
        from domain.instruments.instrument import Option

        return [
            Option.from_leg(
                self._chain.underlying,
                self._chain.exchange,
                self._chain.expiry,
                s.strike,
                "CE",
                s.call,
                data_provider=self._provider,
            )
            for s in self._chain.strikes
        ]

    @property
    def puts(self):
        from domain.instruments.instrument import Option

        return [
            Option.from_leg(
                self._chain.underlying,
                self._chain.exchange,
                self._chain.expiry,
                s.strike,
                "PE",
                s.put,
                data_provider=self._provider,
            )
            for s in self._chain.strikes
        ]

    def pcr(self) -> Decimal | None:
        """Put/Call ratio from open interest across the chain."""
        call_oi = sum((s.call.oi or 0) for s in self._chain.strikes)
        put_oi = sum((s.put.oi or 0) for s in self._chain.strikes)
        if call_oi == 0:
            return None
        return Decimal(put_oi) / Decimal(call_oi)

    def max_pain(self) -> Decimal | None:
        """Strike at which total option-writer payout is minimized."""
        strikes = [s.strike for s in self._chain.strikes]
        if not strikes:
            return None
        pain: dict[Decimal, int] = {}
        for k in strikes:
            total = 0
            for s in self._chain.strikes:
                coi = s.call.oi or 0
                poi = s.put.oi or 0
                total += coi * max(0, int(s.strike - k)) + poi * max(0, int(k - s.strike))
            pain[k] = total
        return min(pain, key=pain.get)

    def itm(self, side: str = "CE", spot: Decimal | None = None) -> list:
        """Return in-the-money options.

        For calls: strike < spot
        For puts: strike > spot
        """
        s = spot or self._chain.spot
        if s is None:
            return []
        from domain.instruments.instrument import Option

        result = []
        for strike_row in self._chain.strikes:
            if side == "CE" and strike_row.strike < s:
                result.append(
                    Option.from_leg(
                        self._chain.underlying,
                        self._chain.exchange,
                        self._chain.expiry,
                        strike_row.strike,
                        "CE",
                        strike_row.call,
                        data_provider=self._provider,
                    )
                )
            elif side == "PE" and strike_row.strike > s:
                result.append(
                    Option.from_leg(
                        self._chain.underlying,
                        self._chain.exchange,
                        self._chain.expiry,
                        strike_row.strike,
                        "PE",
                        strike_row.put,
                        data_provider=self._provider,
                    )
                )
        return result

    def otm(self, side: str = "CE", spot: Decimal | None = None) -> list:
        """Return out-of-the-money options.

        For calls: strike > spot
        For puts: strike < spot
        """
        s = spot or self._chain.spot
        if s is None:
            return []
        from domain.instruments.instrument import Option

        result = []
        for strike_row in self._chain.strikes:
            if side == "CE" and strike_row.strike > s:
                result.append(
                    Option.from_leg(
                        self._chain.underlying,
                        self._chain.exchange,
                        self._chain.expiry,
                        strike_row.strike,
                        "CE",
                        strike_row.call,
                        data_provider=self._provider,
                    )
                )
            elif side == "PE" and strike_row.strike < s:
                result.append(
                    Option.from_leg(
                        self._chain.underlying,
                        self._chain.exchange,
                        self._chain.expiry,
                        strike_row.strike,
                        "PE",
                        strike_row.put,
                        data_provider=self._provider,
                    )
                )
        return result

    # ── Expiry navigation ──────────────────────────────────────────────

    @property
    def current_expiry(self) -> str | None:
        """The expiry this snapshot represents (``None`` if unexpired)."""
        return self._chain.expiry or None

    @property
    def nearest_expiry(self) -> str | None:
        """Expiry closest to today among the stored expiries."""
        expiries = self.expiries
        if not expiries:
            return None
        today = date.today()
        return min(expiries, key=lambda e: self._expiry_distance(e, today))

    @property
    def next_expiry(self) -> str | None:
        """The expiry immediately after ``current_expiry`` (``None`` if last)."""
        expiries = sorted(self.expiries)
        cur = self.current_expiry
        if cur in expiries:
            idx = expiries.index(cur)
            return expiries[idx + 1] if idx + 1 < len(expiries) else None
        return None

    @staticmethod
    def _expiry_distance(expiry: str, today: date) -> int:
        d = OptionChain._parse_expiry(expiry)
        return abs((d - today).days) if d is not None else 10 ** 9

    @staticmethod
    def _parse_expiry(expiry: str | None) -> date | None:
        if not expiry:
            return None
        for fmt in ("%Y-%m-%d", "%Y%m%d"):
            try:
                return datetime.strptime(expiry, fmt).date()
            except ValueError:
                continue
        return None

    def strike(self, price) -> tuple | None:
        """Return ``(call, put)`` :class:`Option` at ``price`` (``None`` if absent)."""
        target = Decimal(str(price))
        row = next((s for s in self._chain.strikes if s.strike == target), None)
        if row is None:
            return None
        from domain.instruments.instrument import Option

        call = Option.from_leg(
            self._chain.underlying,
            self._chain.exchange,
            self._chain.expiry,
            row.strike,
            "CE",
            row.call,
            data_provider=self._provider,
        )
        put = Option.from_leg(
            self._chain.underlying,
            self._chain.exchange,
            self._chain.expiry,
            row.strike,
            "PE",
            row.put,
            data_provider=self._provider,
        )
        return (call, put)

    def expiry_chain(self, expiry: date | str) -> OptionChain:
        """Fetch the chain for a *different* expiry.

        Delegates to the backing ``DataProvider`` when one is wired; otherwise
        returns a shallow copy of this snapshot pinned to the requested expiry
        (no live data is fetched).
        """
        expiry_str = expiry.strftime("%Y-%m-%d") if isinstance(expiry, date) else str(expiry)
        if self._provider is None:
            return OptionChain(
                OptionChainVO(
                    underlying=self._chain.underlying,
                    exchange=self._chain.exchange,
                    expiry=expiry_str,
                    spot=self._chain.spot,
                    strikes=self._chain.strikes,
                ),
                data_provider=self._provider,
            )
        iid = InstrumentId.index(self._chain.exchange, self._chain.underlying)
        vo = self._provider.get_option_chain(
            iid, expiry=self._parse_expiry(expiry_str)
        )
        return OptionChain(vo, data_provider=self._provider)

    # ── Surface analytics ──────────────────────────────────────────────

    def greeks(self) -> GreeksSurface:
        """Build a :class:`GreeksSurface` from the per-strike call greeks."""
        data = {s.strike: Greeks.from_dict(s.call.greeks) for s in self._chain.strikes}
        return GreeksSurface(
            underlying=self._chain.underlying,
            expiry=self._chain.expiry,
            spot=self._chain.spot,
            data=data,
        )

    def iv_surface(self) -> IVSurface:
        """Build an :class:`IVSurface` from the per-strike call/put IVs."""
        data = {s.strike: (s.call.iv, s.put.iv) for s in self._chain.strikes}
        return IVSurface(
            underlying=self._chain.underlying,
            expiry=self._chain.expiry,
            spot=self._chain.spot,
            data=data,
        )

    def volatility_surface(self) -> VolatilitySurface:
        """Build a :class:`VolatilitySurface`.

        Limited to the single expiry present in this snapshot. A full
        multi-expiry term structure requires a provider that exposes all
        expiries at once (wire it in the integration phase).
        """
        surfaces = {self._chain.expiry: self.iv_surface()} if self._chain.expiry else {}
        return VolatilitySurface(underlying=self._chain.underlying, surfaces=surfaces)

    def gamma_exposure(self) -> dict[Decimal, Decimal]:
        """Per-strike gamma exposure ≈ ``gamma × open_interest`` (call leg)."""
        out: dict[Decimal, Decimal] = {}
        for s in self._chain.strikes:
            gamma = Greeks.from_dict(s.call.greeks).gamma
            oi = (s.call.oi or 0) + (s.put.oi or 0)
            out[s.strike] = gamma * Decimal(oi)
        return out

    def delta_exposure(self) -> dict[Decimal, Decimal]:
        """Per-strike delta exposure ≈ ``delta × OI`` (calls + puts signed)."""
        out: dict[Decimal, Decimal] = {}
        for s in self._chain.strikes:
            call_g = Greeks.from_dict(s.call.greeks)
            put_g = Greeks.from_dict(s.put.greeks)
            out[s.strike] = call_g.delta * Decimal(s.call.oi or 0) + put_g.delta * Decimal(
                s.put.oi or 0
            )
        return out

    def refresh(self) -> OptionChain:
        """Re-fetch this chain's current expiry from the provider, if wired."""
        if self._provider is None:
            return self
        iid = InstrumentId.index(self._chain.exchange, self._chain.underlying)
        vo = self._provider.get_option_chain(
            iid, expiry=self._parse_expiry(self._chain.expiry)
        )
        return OptionChain(vo, data_provider=self._provider)

    def history(
        self,
        strike,
        right: str,
        timeframe: str = "1D",
        days: int = 120,
    ) -> HistoricalSeries:
        """Historical bars for the option at ``strike``/``right``.

        Delegates to the backing ``DataProvider`` when wired; otherwise returns
        an empty :class:`HistoricalSeries` spanning ``days`` ending today.
        """
        expiry_date = self._parse_expiry(self._chain.expiry)
        if self._provider is None or expiry_date is None:
            end = date.today()
            start = end - timedelta(days=days)
            return HistoricalSeries(
                bars=[],
                coverage=DateRange(start=start, end=end),
                instrument=InstrumentRef(
                    symbol=self._chain.underlying, exchange=self._chain.exchange
                ),
                timeframe=timeframe,
            )
        iid = InstrumentId.option(
            self._chain.exchange,
            self._chain.underlying,
            expiry_date,
            Decimal(str(strike)),
            right,
        )
        return self._provider.get_history_series(
            iid, timeframe=timeframe, lookback_days=days
        )

    def subscribe(self, callback=None, *, depth: bool = False):
        """Subscribe the underlying instrument."""
        if self._provider is None:
            return None
        from domain.instruments.instrument import Instrument
        from domain.instruments.instrument_id import InstrumentId

        underlying = Instrument(
            InstrumentId.index(self._chain.exchange, self._chain.underlying),
            data_provider=self._provider,
        )
        return underlying.subscribe(callback or (lambda *a, **k: None), depth=depth)

    @classmethod
    def empty(cls) -> OptionChain:
        """Return an empty option chain."""
        return cls(OptionChainVO(underlying="", exchange="", expiry="", spot=None, strikes=[]))

    def __repr__(self) -> str:
        return (
            f"OptionChain(underlying={self._chain.underlying}, "
            f"expiry={self._chain.expiry}, strikes={len(self._chain.strikes)})"
        )
