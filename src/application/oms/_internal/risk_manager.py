"""Pre-trade risk management.

Pre-trade risk checks run inside the OMS lock before an order is submitted. All checks
are deterministic and read-only on the provided state.

Concurrency contract (Phase A / A2 + A3)
-----------------------------------------
Every mutator on :class:`RiskManager` is protected by an internal
``threading.RLock``. The previous implementation had no lock, which meant
``set_kill_switch`` and ``update_daily_pnl`` could be observed mid-update
by a concurrent ``check_order`` call. This was acceptable only because the
OMS held an outer lock for the place_order path; anything outside the OMS
(operator CLI, kill-switch webhook, dashboard query) raced.

The fix is internal to :class:`RiskManager` so the contract holds for any
caller, OMS or not.

Daily PnL rollover (Phase A / A2)
---------------------------------
``_daily_pnl`` is now reset by :meth:`reset_daily_pnl`, which must be
called by an external scheduler at the configured rollover hour (default
00:00 IST). :class:`application.oms.daily_pnl_reset_scheduler.DailyPnlResetScheduler`
is the canonical implementation. Without that scheduler, the running
total will accumulate across the IST 00:00 boundary and the daily-loss
check will block orders the next morning.

CapitalProvider support (P2-2)
-------------------------------
RiskManager now accepts either ``capital_fn`` (legacy) or ``capital_provider``
(new protocol-based approach). The CapitalProvider protocol solves the
initialization ordering problem by deferring capital retrieval until
funds() is actually needed.

Loss-based circuit breaker (B1)
-------------------------------
A :class:`LossCircuitBreaker` runs alongside the daily-loss check. Unlike
the daily-loss check (which resets at 00:00 IST), the loss circuit breaker
uses a rolling 24-hour window and trips when cumulative losses exceed a
configurable percentage of capital. It is independent of the kill switch
and maintains its own observable state.
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from dataclasses import dataclass, replace
from decimal import Decimal
from typing import Any, Protocol, runtime_checkable

from application.oms._internal.loss_circuit_breaker import (
    LossCircuitBreaker,
    LossCircuitBreakerConfig,
)
from application.oms.capital_provider import CapitalProvider, FixedCapitalProvider
from application.oms.position_manager import PositionManager
from domain import Order
from domain.constants import (
    RISK_DAILY_LOSS_PERCENT,
    RISK_GROSS_PERCENT,
    RISK_MARGIN_SAFETY_MULTIPLIER,
    RISK_POSITION_PERCENT,
)
from domain.constants.defaults import RISK_FALLBACK_CAPITAL
from domain.exchange_segments import is_derivative_segment
from domain.ports.margin_provider import MarginProviderPort
from domain.risk.notional import effective_notional
from domain.utils.price import is_tick_aligned

logger = logging.getLogger(__name__)


@runtime_checkable
class InstrumentProvider(Protocol):
    """Narrow protocol for instrument lookups (tick size, lot size, etc.)."""

    def resolve(self, symbol: str, exchange: str) -> Any: ...


@dataclass(frozen=True)
class RiskConfig:
    max_daily_loss_pct: Decimal = Decimal(str(RISK_DAILY_LOSS_PERCENT))  # of capital
    max_position_pct: Decimal = Decimal(str(RISK_POSITION_PERCENT))  # of capital per symbol
    max_gross_exposure_pct: Decimal = Decimal(str(RISK_GROSS_PERCENT))  # of capital
    kill_switch: bool = False
    margin_safety_multiplier: Decimal = Decimal(str(RISK_MARGIN_SAFETY_MULTIPLIER))
    enable_margin_check: bool = True


@dataclass(frozen=True)
class RiskResult:
    allowed: bool
    reason: str | None = None


class RiskManager:
    """Deterministic, stateless risk checks.

    State held:

    * ``_config`` — frozen :class:`RiskConfig`; replaced atomically on
      :meth:`set_kill_switch`.
    * ``_daily_pnl`` — running total of realised + unrealised PnL for
      the current day. Reset to 0 by :meth:`reset_daily_pnl`.
    * ``_loss_cb`` — :class:`LossCircuitBreaker` for rolling-window loss
      detection (B1).

    All state mutations are guarded by ``_lock``. ``check_order`` takes
    the lock for the duration of the read so an interleaved
    ``set_kill_switch`` or ``update_daily_pnl`` cannot produce a
    half-observed state.
    """

    def __init__(
        self,
        position_manager: PositionManager,
        config: RiskConfig,
        capital_fn: Callable[[], Decimal] | None = None,
        capital_provider: CapitalProvider | None = None,
        loss_cb_config: LossCircuitBreakerConfig | None = None,
        margin_provider: MarginProviderPort | None = None,
        instrument_provider: InstrumentProvider | None = None,
    ) -> None:
        self._position_manager = position_manager
        self._config = config
        self._margin_provider = margin_provider
        self._instrument_provider = instrument_provider

        # Support both old capital_fn and new capital_provider (P2-2)
        if capital_provider is not None:
            self._capital_provider = capital_provider
        elif capital_fn is not None:
            # Wrap legacy capital_fn in adapter
            class LegacyCapitalAdapter(CapitalProvider):
                def __init__(self, fn):
                    self._fn = fn

                def get_available_balance(self) -> Decimal:
                    return self._fn()

            self._capital_provider = LegacyCapitalAdapter(capital_fn)
        else:
            # Default to fixed capital
            self._capital_provider = FixedCapitalProvider(RISK_FALLBACK_CAPITAL)

        self._daily_pnl: Decimal = Decimal("0")
        # Lock that protects _config, _daily_pnl, and the derived
        # reads in check_order. RLock (not Lock) so the OMS may
        # legitimately call check_order from inside its own critical
        # section without deadlocking.
        self._lock = threading.RLock()
        # Observability: monotonic counters for reset / kill-switch
        # events. Useful for alerting ("daily PnL reset fired today").
        self._reset_count: int = 0
        self._kill_switch_toggles: int = 0
        self._last_reset_at: float = 0.0  # time.time() at last reset

        # Loss-based circuit breaker
        self._loss_cb = LossCircuitBreaker(config=loss_cb_config)

    def _resolve_market_context(
        self, order: Order
    ) -> tuple[Decimal | None, Decimal | None, Any | None]:
        """Best-effort LTP/ref price and multiplier for notional sizing.

        Priority for ref price: order.price (handled by effective_notional),
        then open position LTP, then instrument last/ltp attributes.
        """
        ref: Decimal | None = None
        mult: Decimal | None = None
        instrument: Any | None = None

        current = self._position_manager.get_position(order.symbol, order.exchange)
        if current is not None:
            if current.ltp and current.ltp > 0:
                ref = current.ltp
            elif current.avg_price and current.avg_price > 0:
                ref = current.avg_price
            if getattr(current, "multiplier", None) and current.multiplier > 0:
                mult = current.multiplier

        if self._instrument_provider is not None:
            try:
                instrument = self._instrument_provider.resolve(order.symbol, order.exchange)
            except Exception as exc:
                logger.warning(
                    "notional_instrument_lookup_failed",
                    extra={
                        "symbol": order.symbol,
                        "exchange": order.exchange,
                        "error": str(exc),
                    },
                )
                instrument = None
            if instrument is not None:
                for attr in ("ltp", "last_price", "last_traded_price"):
                    raw = getattr(instrument, attr, None)
                    if raw is not None:
                        try:
                            cand = Decimal(str(raw))
                            if cand > 0:
                                ref = cand
                                break
                        except Exception:
                            pass
                raw_m = getattr(instrument, "multiplier", None)
                if raw_m is not None:
                    try:
                        m = Decimal(str(raw_m))
                        if m > 0:
                            mult = m
                    except Exception:
                        pass

        return ref, mult, instrument

    # -- Margin check (B3) --

    def _check_margin(self, order: Order) -> RiskResult:
        """Check margin requirement for derivative orders.

        Fail-closed design: if margin provider is unavailable or the API
        call fails, the order is rejected. This is safer than allowing an
        unvalidated F&O order through to the broker.

        Args:
            order: The order to validate.

        Returns:
            RiskResult indicating whether the margin check passed.
        """
        if self._margin_provider is None:
            logger.warning(
                "margin_check_no_provider",
                extra={
                    "symbol": order.symbol,
                    "exchange": order.exchange,
                    "quantity": order.quantity,
                },
            )
            return RiskResult(False, "F&O order rejected: no margin provider configured")

        try:
            margin_result = self._margin_provider.calculate_margin_for_order(
                symbol=order.symbol,
                exchange=order.exchange,
                quantity=order.quantity,
                price=order.price,
                product_type=order.product_type.value
                if hasattr(order.product_type, "value")
                else str(order.product_type),
                order_type=order.order_type.value
                if hasattr(order.order_type, "value")
                else str(order.order_type),
            )
        except Exception as exc:
            # Fail-closed: any unexpected error -> reject order
            logger.error(
                "margin_check_error",
                extra={
                    "symbol": order.symbol,
                    "exchange": order.exchange,
                    "error": str(exc),
                },
            )
            return RiskResult(False, f"F&O order rejected: margin check error: {exc}")

        required_with_buffer = margin_result.required_margin * self._config.margin_safety_multiplier

        # Check if available margin covers the REQUIRED margin WITH the safety buffer
        if margin_result.available_margin < required_with_buffer:
            logger.warning(
                "margin_check_insufficient",
                extra={
                    "symbol": order.symbol,
                    "exchange": order.exchange,
                    "required_margin": str(margin_result.required_margin),
                    "required_with_buffer": str(required_with_buffer),
                    "available_margin": str(margin_result.available_margin),
                },
            )
            return RiskResult(
                False,
                f"Insufficient margin for {order.symbol}: "
                f"required={margin_result.required_margin} "
                f"(with buffer: {required_with_buffer}), "
                f"available={margin_result.available_margin}",
            )

        logger.info(
            "margin_check_passed",
            extra={
                "symbol": order.symbol,
                "exchange": order.exchange,
                "required_margin": str(margin_result.required_margin),
                "available_margin": str(margin_result.available_margin),
            },
        )
        return RiskResult(True)

    # -- Public API --

    def check_order(self, order: Order) -> RiskResult:
        """Check whether ``order`` passes all configured risk limits.

        Thread-safe. Holds ``_lock`` for the duration of the read so a
        concurrent ``set_kill_switch`` cannot produce a half-observed
        config.
        """
        with self._lock:
            if self._config.kill_switch:
                return RiskResult(False, "Kill switch is active")

            # Loss circuit breaker check (before capital check)
            cb_allowed, cb_reason = self._loss_cb.allow_trading()
            if not cb_allowed:
                return RiskResult(False, cb_reason)

            # Tick size alignment check (pre-trade)
            if self._instrument_provider is not None and order.price > 0:
                try:
                    instrument = self._instrument_provider.resolve(
                        order.symbol, order.exchange
                    )
                    if instrument is not None:
                        tick = Decimal(str(getattr(instrument, "tick_size", 0.05)))
                        if tick > 0 and not is_tick_aligned(order.price, tick):
                            return RiskResult(
                                False,
                                f"Price {order.price} not aligned to tick size {tick}",
                            )
                except Exception as exc:
                    logger.warning(
                        "tick_check_instrument_lookup_failed",
                        extra={
                            "symbol": order.symbol,
                            "exchange": order.exchange,
                            "error": str(exc),
                        },
                    )

            capital = self._capital_provider.get_available_balance()
            if capital <= 0:
                return RiskResult(False, "Insufficient capital")

            # F&O margin check (derivative segments only)
            if self._config.enable_margin_check and is_derivative_segment(order.exchange):
                margin_result = self._check_margin(order)
                if not margin_result.allowed:
                    return margin_result

            # Effective notional: never treat bare quantity as rupee notional.
            ref_price, mult, instrument = self._resolve_market_context(order)
            notional = effective_notional(
                order.quantity,
                order.price,
                ref_price=ref_price,
                multiplier=mult,
                instrument=instrument,
            )
            if notional is None:
                return RiskResult(
                    False,
                    f"Cannot size risk for {order.symbol}: no limit/ref price "
                    f"(MARKET orders require LTP/ref price)",
                )

            # Per-symbol concentration
            current = self._position_manager.get_position(order.symbol, order.exchange)
            current_notional = (
                Decimal(abs(current.quantity))
                * current.avg_price
                * (current.multiplier if getattr(current, "multiplier", None) else Decimal("1"))
                if current
                else Decimal("0")
            )
            if (current_notional + notional) / capital * 100 > self._config.max_position_pct:
                return RiskResult(False, f"Exceeds max position pct for {order.symbol}")

            # Gross exposure
            positions = self._position_manager.get_positions()
            gross = sum(
                Decimal(abs(p.quantity))
                * p.avg_price
                * (p.multiplier if getattr(p, "multiplier", None) else Decimal("1"))
                for p in positions
            )
            if (gross + notional) / capital * 100 > self._config.max_gross_exposure_pct:
                return RiskResult(False, "Exceeds max gross exposure pct")

            # Daily loss
            if (
                self._daily_pnl < 0
                and abs(self._daily_pnl) / capital * 100 >= self._config.max_daily_loss_pct
            ):
                return RiskResult(False, "Daily loss limit reached")

            return RiskResult(True)

    def update_daily_pnl(self, pnl: Decimal) -> None:
        """Update running daily PnL (called by portfolio manager).

        Thread-safe. Replaces the running total atomically; readers
        under ``_lock`` will see either the old or the new value, not a
        partially-written one.

        B1: Also records the PnL delta in the loss circuit breaker so
        the rolling-window loss threshold is updated.
        """
        with self._lock:
            previous_pnl = self._daily_pnl
            self._daily_pnl = pnl

            # Record the PnL delta (not the absolute value) in the
            # loss circuit breaker. The delta represents the realised /
            # unrealised change since the last update.
            delta = pnl - previous_pnl
            capital = self._capital_provider.get_available_balance()
            self._loss_cb.record_loss(delta, capital)

    def set_kill_switch(self, active: bool) -> None:
        """Enable or disable the kill switch by replacing the frozen config.

        Thread-safe. A concurrent ``check_order`` will see either the
        old config (kill switch as it was) or the new one (kill switch
        flipped), but never a torn read of the dataclass.
        """
        with self._lock:
            previous = self._config.kill_switch
            self._config = replace(self._config, kill_switch=active)
            if previous != active:
                self._kill_switch_toggles += 1
                logger.warning(
                    "kill_switch_toggled",
                    extra={"new_state": active, "previous": previous},
                )

    def is_kill_switch_active(self) -> bool:
        """Check if kill switch is currently active.

        P4-5: Thread-safe read of kill switch status.

        Returns
        -------
        bool:
            True if kill switch prevents order execution.
        """
        with self._lock:
            return self._config.kill_switch

    def reset_daily_pnl(self) -> None:
        """Reset the daily PnL to zero.

        Called by :class:`DailyPnlResetScheduler` at the configured
        rollover hour (default 00:00 IST). Safe to call manually from
        tests or operator scripts.

        Thread-safe. Increments ``_reset_count`` and records
        ``_last_reset_at`` so an SRE can confirm the rollover fired.
        """
        import time as _time

        with self._lock:
            self._daily_pnl = Decimal("0")
            self._reset_count += 1
            self._last_reset_at = _time.time()
        logger.info("daily_pnl_reset", extra={"reset_count": self._reset_count})

    def reset_loss_circuit_breaker(self) -> None:
        """Manually reset the loss-based circuit breaker.

        B1: Operators can call this after investigating a trip. The
        circuit transitions OPEN -> COOLDOWN (requiring a further wait)
        or COOLDOWN -> CLOSED (immediate re-enable).

        Thread-safe. Delegates to :class:`LossCircuitBreaker`.
        """
        self._loss_cb.reset()

    # -- Observability (read-only) --

    @property
    def daily_pnl(self) -> Decimal:
        """Current daily PnL snapshot. Thread-safe."""
        with self._lock:
            return self._daily_pnl

    @property
    def kill_switch(self) -> bool:
        """Current kill-switch state. Thread-safe."""
        with self._lock:
            return self._config.kill_switch

    @property
    def loss_circuit_breaker(self) -> LossCircuitBreaker:
        """Access the loss circuit breaker for inspection.

        B1: Read-only access to the circuit breaker. Callers should not
        mutate it directly; use :meth:`reset_loss_circuit_breaker`.
        """
        return self._loss_cb

    def snapshot(self) -> dict:
        """Return a JSON-serializable view of risk-manager state.

        Useful for ``/healthz`` and SRE dashboards. Locks are taken
        only briefly to read the scalar fields.
        """
        import time as _time

        with self._lock:
            base = {
                "kill_switch": self._config.kill_switch,
                "daily_pnl": str(self._daily_pnl),
                "max_daily_loss_pct": str(self._config.max_daily_loss_pct),
                "max_position_pct": str(self._config.max_position_pct),
                "max_gross_exposure_pct": str(self._config.max_gross_exposure_pct),
                "reset_count": self._reset_count,
                "kill_switch_toggles": self._kill_switch_toggles,
                "last_reset_at": self._last_reset_at,
                "seconds_since_last_reset": (
                    _time.time() - self._last_reset_at if self._last_reset_at > 0 else None
                ),
            }

        # Append loss circuit breaker state (takes its own lock).
        base["loss_circuit_breaker"] = self._loss_cb.snapshot()
        return base
