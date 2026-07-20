"""OptionChain — first-class aggregate, composed of Option instruments.

chain = nifty.option_chain()
chain.atm              # Option (call at the ATM strike)
chain.calls            # list[Option]
chain.puts             # list[Option]
chain.pcr()            # put/call open-interest ratio
chain.max_pain()       # max-pain strike
chain.itm()            # in-the-money options
chain.otm()            # out-of-the-money options
chain.select_strikes("ATM")          # StrikeSelection with Option CE/PE
chain.select_strikes("OTM", steps=5)
chain.expiry_at(0)                   # TradeHull-style expiry offset
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING

from domain.candles.historical import DateRange, HistoricalSeries, InstrumentRef
from domain.entities.options import OptionChain as OptionChainVO
from domain.instruments.instrument_id import InstrumentId
from domain.options.greeks import Greeks
from domain.options.strike_selection import StrikeSelection
from domain.options.surfaces import GreeksSurface, IVSurface, VolatilitySurface

if TYPE_CHECKING:
    from domain.instruments.instrument import Option
    from domain.ports.order_service import OrderServicePort
    from domain.ports.protocols import DataProvider


class OptionChain:
    """Rich query surface over a normalized option-chain snapshot."""

    def __init__(
        self,
        chain: OptionChainVO,
        *,
        data_provider: DataProvider | None = None,
        provider: DataProvider | None = None,
        order_service: OrderServicePort | None = None,
        available_expiries: Sequence[str | date] | None = None,
    ) -> None:
        self._chain = chain
        # Accept both keyword spellings: ``data_provider`` (canonical port name)
        # and ``provider`` (used by call sites in ``instrument.py``).
        self._provider = data_provider or provider
        self._order_service = order_service
        self._available_expiries: tuple[str, ...] = self._normalize_expiry_list(available_expiries)

    def _option_from_leg(self, strike, right: str, leg) -> Option:
        """Build Option leg with data + OMS stamps (PR-3b)."""
        from domain.instruments.instrument import Option

        return Option.from_leg(
            self._chain.underlying,
            self._chain.exchange,
            self._chain.expiry,
            strike,
            right,
            leg,
            data_provider=self._provider,
            order_service=self._order_service,
        )

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
        if self._available_expiries:
            return self._available_expiries
        return (self._chain.expiry,) if self._chain.expiry else ()

    @property
    def spot(self) -> Decimal | None:
        return self._chain.spot

    @property
    def strikes(self):
        return self._chain.strikes

    @staticmethod
    def _normalize_expiry_list(
        available: Sequence[str | date] | None,
    ) -> tuple[str, ...]:
        if not available:
            return ()
        out: list[str] = []
        for e in available:
            if isinstance(e, date):
                out.append(e.strftime("%Y-%m-%d"))
            else:
                s = str(e).strip()
                if s:
                    out.append(s)
        return tuple(out)

    def with_expiries(self, expiries: Sequence[str | date]) -> OptionChain:
        """Return a chain view with an explicit multi-expiry calendar."""
        return OptionChain(
            self._chain,
            data_provider=self._provider,
            order_service=self._order_service,
            available_expiries=expiries,
        )

    # ── Queries ─────────────────────────────────────────────────────

    def _atm_strike(self) -> Decimal | None:
        spot = self._chain.spot
        if spot is None or not self._chain.strikes:
            return None
        return min(
            (s.strike for s in self._chain.strikes),
            key=lambda k: abs(k - spot),
        )

    def _sorted_strikes(self) -> list[Decimal]:
        return sorted({s.strike for s in self._chain.strikes})

    def _pair_at(self, strike: Decimal) -> tuple | None:
        return self.strike(strike)

    def select_strikes(
        self,
        style: str = "ATM",
        steps: int = 0,
    ) -> StrikeSelection:
        """TradeHull-style strike selection returning stamped Option instruments.

        Parameters
        ----------
        style:
            ``ATM`` — nearest strike to spot (CE+PE same strike).
            ``OTM`` — call steps above ATM, put steps below.
            ``ITM`` — call steps below ATM, put steps above.
        steps:
            Distance in strike-grid steps from ATM (0 with ATM is ATM;
            for OTM/ITM, ``steps`` defaults to 1 if 0 is passed).
        """
        style_u = str(style).strip().upper()
        if style_u not in {"ATM", "OTM", "ITM"}:
            raise ValueError(f"Unknown select_strikes style {style!r}; expected ATM|OTM|ITM")
        grid = self._sorted_strikes()
        atm = self._atm_strike()
        if not grid or atm is None:
            return StrikeSelection(style=style_u, steps=steps, strike=None, ce=None, pe=None)

        atm_idx = min(range(len(grid)), key=lambda i: abs(grid[i] - atm))

        if style_u == "ATM":
            k = grid[atm_idx]
            pair = self._pair_at(k)
            ce, pe = pair if pair else (None, None)
            return StrikeSelection(
                style=style_u,
                steps=0,
                strike=k,
                ce=ce,
                pe=pe,
                ce_strike=k,
                pe_strike=k,
            )

        n = max(int(steps), 1)
        if style_u == "OTM":
            ce_i = min(atm_idx + n, len(grid) - 1)
            pe_i = max(atm_idx - n, 0)
        else:  # ITM
            ce_i = max(atm_idx - n, 0)
            pe_i = min(atm_idx + n, len(grid) - 1)

        ce_k, pe_k = grid[ce_i], grid[pe_i]
        ce_pair = self._pair_at(ce_k)
        pe_pair = self._pair_at(pe_k)
        ce = ce_pair[0] if ce_pair else None
        pe = pe_pair[1] if pe_pair else None
        shared = ce_k if ce_k == pe_k else None
        return StrikeSelection(
            style=style_u,
            steps=n,
            strike=shared,
            ce=ce,
            pe=pe,
            ce_strike=ce_k,
            pe_strike=pe_k,
        )

    def expiry_at(self, offset: int = 0) -> date | None:
        """TradeHull-style expiry offset: 0 = nearest/current, 1 = next, …

        Uses :attr:`expiries` (multi-expiry calendar when provided via
        ``with_expiries`` / provider); otherwise the snapshot's single expiry.
        """
        off = int(offset)
        if off < 0:
            raise ValueError(f"expiry offset must be >= 0, got {offset}")
        parsed: list[date] = []
        for e in self.expiries:
            d = self._parse_expiry(e)
            if d is not None:
                parsed.append(d)
        if not parsed:
            return None
        # Sort chronologically; prefer on-or-after today for offset 0
        today = date.today()
        future = sorted(d for d in parsed if d >= today)
        sorted(d for d in parsed if d < today)
        ordered = future if future else sorted(parsed)
        if off >= len(ordered):
            raise ValueError(
                f"expiry offset {off} out of range; "
                f"have {len(ordered)} expiries: {[d.isoformat() for d in ordered]}"
            )
        return ordered[off]

    def chain_at_offset(self, offset: int = 0) -> OptionChain:
        """Fetch (or pin) the chain for :meth:`expiry_at` ``offset``."""
        target = self.expiry_at(offset)
        if target is None:
            return self
        cur = self._parse_expiry(self._chain.expiry)
        if cur == target:
            return self
        return self.expiry_chain(target)

    @property
    def atm(self):
        """The ATM call as a full Option instrument."""
        strike = self._atm_strike()
        if strike is None:
            return None
        row = next((s for s in self._chain.strikes if s.strike == strike), None)
        if row is None:
            return None
        return self._option_from_leg(strike, "CE", row.call)

    @property
    def calls(self):
        return [self._option_from_leg(s.strike, "CE", s.call) for s in self._chain.strikes]

    @property
    def puts(self):
        return [self._option_from_leg(s.strike, "PE", s.put) for s in self._chain.strikes]

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
        result = []
        for strike_row in self._chain.strikes:
            if side == "CE" and strike_row.strike < s:
                result.append(self._option_from_leg(strike_row.strike, "CE", strike_row.call))
            elif side == "PE" and strike_row.strike > s:
                result.append(self._option_from_leg(strike_row.strike, "PE", strike_row.put))
        return result

    def otm(self, side: str = "CE", spot: Decimal | None = None) -> list:
        """Return out-of-the-money options.

        For calls: strike > spot
        For puts: strike < spot
        """
        s = spot or self._chain.spot
        if s is None:
            return []
        result = []
        for strike_row in self._chain.strikes:
            if side == "CE" and strike_row.strike > s:
                result.append(self._option_from_leg(strike_row.strike, "CE", strike_row.call))
            elif side == "PE" and strike_row.strike < s:
                result.append(self._option_from_leg(strike_row.strike, "PE", strike_row.put))
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
        return abs((d - today).days) if d is not None else 10**9

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
        return (
            self._option_from_leg(row.strike, "CE", row.call),
            self._option_from_leg(row.strike, "PE", row.put),
        )

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
                order_service=self._order_service,
                available_expiries=self._available_expiries or None,
            )
        iid = InstrumentId.index(self._chain.exchange, self._chain.underlying)
        vo = self._provider.get_option_chain(iid, expiry=self._parse_expiry(expiry_str))
        return OptionChain(
            vo,
            data_provider=self._provider,
            order_service=self._order_service,
            available_expiries=self._available_expiries or None,
        )

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
        vo = self._provider.get_option_chain(iid, expiry=self._parse_expiry(self._chain.expiry))
        return OptionChain(
            vo,
            data_provider=self._provider,
            order_service=self._order_service,
            available_expiries=self._available_expiries or None,
        )

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
        return self._provider.get_history_series(iid, timeframe=timeframe, lookback_days=days)

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
