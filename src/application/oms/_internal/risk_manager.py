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

Decomposition
-------------
The heavy lifting has been extracted into focused modules that this class
delegates to (no circular imports):

* :class:`~application.oms._internal.margin_checker.MarginChecker` —
  F&O margin check + pending-exposure bookkeeping + market-context resolution.
* :class:`~application.oms._internal.kill_switch.KillSwitch` —
  kill-switch state + ``KILL_SWITCH_TOGGLED`` publishing.
* :class:`~application.oms._internal.daily_pnl_tracker.DailyPnlTracker` —
  daily PnL total + ``RISK_LIMIT_BREACHED`` publishing.
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from decimal import Decimal
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from domain.portfolio.risk_profile import RiskProfile
    from domain.risk.policy import KillSwitch as DomainKillSwitch

from application.oms._internal.daily_pnl_tracker import (
    DailyPnlTracker,
    RISK_LIMIT_BREACH_THRESHOLD,
)
from application.oms._internal.kill_switch import KillSwitch, KILL_SWITCH_MODE
from application.oms._internal.loss_circuit_breaker import (
    LossCircuitBreaker,
    LossCircuitBreakerConfig,
)
from application.oms._internal.margin_checker import MarginChecker
from application.oms._internal.throttler import Throttler
from application.oms._internal.trading_state import TradingState, TradingStateEnum
from application.oms._internal.risk_types import (
    InstrumentProvider,
    RiskConfig,
    RiskResult,
    risk_result_from_domain,
)
from application.oms.capital_provider import CapitalProvider, FixedCapitalProvider
from application.oms.position_manager import PositionManager
from domain import Order
from domain.constants.defaults import RISK_FALLBACK_CAPITAL
from domain.constants.market import DEFAULT_TICK_SIZE
from domain.exchange_segments import is_derivative_segment
from domain.risk.notional import effective_notional
from domain.value_objects.price import is_tick_aligned

logger = logging.getLogger(__name__)


class RiskManager:
    """Deterministic, stateless risk checks.

    State held:

    * ``_config`` — frozen :class:`RiskConfig`; replaced atomically on
      :meth:`set_kill_switch`.
    * ``_daily_pnl`` — session equity delta (current − session-open equity).
      Reset to 0 by :meth:`reset_daily_pnl`.
    * ``_loss_cb`` — :class:`LossCircuitBreaker` for rolling-window loss
      detection (B1).

    All state mutations are guarded by ``_lock``. ``check_order`` takes
    the lock for the duration of the read so an interleaved
    ``set_kill_switch`` or ``update_daily_pnl`` cannot produce a
    half-observed state.

    Kill-switch desk policy (Part 5 §3.1)
    ------------------------------------
    ``KILL_SWITCH_MODE = freeze_all``: when active, *all* order-modifying
    actions are rejected — new risk, cancels/modifies, square-off, and
    ``exit_all``. This is intentional: a compromised process must not be
    able to "emergency exit" destructively. Operators clear the kill
    switch, then flatten. No ``freeze_new_orders_only`` dual-mode.
    """

    #: Desk policy: kill switch freezes every order action (incl. exit_all).
    KILL_SWITCH_MODE = KILL_SWITCH_MODE

    #: Fraction of the daily-loss budget consumed before RISK_LIMIT_BREACHED
    #: fires. Deliberately below 1.0 so operators get a warning before the
    #: hard daily-loss check in check_order starts rejecting orders outright.
    RISK_LIMIT_BREACH_THRESHOLD = RISK_LIMIT_BREACH_THRESHOLD

    def __init__(
        self,
        position_manager: PositionManager,
        config: RiskConfig,
        capital_fn: Callable[[], Decimal] | None = None,
        capital_provider: CapitalProvider | None = None,
        loss_cb_config: LossCircuitBreakerConfig | None = None,
        margin_provider: MarginProviderPort | None = None,
        instrument_provider: InstrumentProvider | None = None,
        on_risk_event: Callable[[str, dict], None] | None = None,
        domain_kill_switch: "DomainKillSwitch | None" = None,
    ) -> None:
        self._position_manager = position_manager
        self._config = config
        self._margin_provider = margin_provider
        self._instrument_provider = instrument_provider
        # Optional event-publish hook: on_risk_event(event_type_value, payload).
        # None by default (no-op) so every existing caller is unaffected.
        self._on_risk_event = on_risk_event
        # Optional domain KillSwitch (REF-4 bridge). When set, check_order
        # consults it in addition to RiskConfig.kill_switch; set_kill_switch
        # keeps both in sync. Default None = legacy config-only path.
        self._domain_kill_switch = domain_kill_switch

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

        # Loss-based circuit breaker
        self._loss_cb = LossCircuitBreaker(config=loss_cb_config)

        # Delegated sub-components (extracted responsibilities).
        self._margin_checker = MarginChecker(
            config=config,
            margin_provider=margin_provider,
            instrument_provider=instrument_provider,
        )
        self._kill_switch = KillSwitch(
            config=config,
            domain_kill_switch=domain_kill_switch,
            on_risk_event=on_risk_event,
        )
        self._daily_pnl_tracker = DailyPnlTracker(
            config=config,
            capital_provider=self._capital_provider.get_available_balance,
            loss_cb=self._loss_cb,
            on_risk_event=on_risk_event,
        )
        self._throttler = Throttler()
        self._trading_state = TradingState()

        # Lock that protects _config, _daily_pnl, and the derived
        # reads in check_order. RLock (not Lock) so the OMS may
        # legitimately call check_order from inside its own critical
        # section without deadlocking.
        self._lock = threading.RLock()

    def release_pending(self, correlation_id: str | None) -> None:
        """Release a pending exposure reservation (idempotent)."""
        self._margin_checker.release_pending(correlation_id)

    # -- Public API --

    def check_order(self, order: Order) -> RiskResult:
        """Check whether ``order`` passes all configured risk limits.

        Thread-safe. Holds ``_lock`` for the duration of the read so a
        concurrent ``set_kill_switch`` cannot produce a half-observed
        config.
        """
        with self._lock:
            if self._kill_switch.is_active():
                return RiskResult(False, "Kill switch is active")

            # Domain KillSwitch bridge (REF-4): optional pure policy object.
            if self._domain_kill_switch is not None:
                domain_ks = risk_result_from_domain(self._domain_kill_switch.check())
                if not domain_ks.allowed:
                    return domain_ks

            # TradingState gate (ACTIVE/REDUCING/HALTED)
            if not self._trading_state.allows_new_order():
                return RiskResult(False, f"Trading halted: state={self._trading_state.state.value}")

            # Loss circuit breaker check (before capital check)
            cb_allowed, cb_reason = self._loss_cb.allow_trading()
            if not cb_allowed:
                return RiskResult(False, cb_reason)

            # Throttler (spec §2 step e: before tick alignment)
            if not self._throttler.allow():
                return RiskResult(False, "Order submission rate limit exceeded")

            # Tick size alignment check (pre-trade)
            if self._instrument_provider is not None and order.price > 0:
                try:
                    instrument = self._instrument_provider.resolve(
                        order.symbol, order.exchange
                    )
                    if instrument is not None:
                        tick = Decimal(str(getattr(instrument, "tick_size", DEFAULT_TICK_SIZE)))
                        price_decimal = order.price.to_decimal() if hasattr(order.price, 'to_decimal') else Decimal(str(order.price))
                        if tick > 0 and not is_tick_aligned(price_decimal, tick):
                            return RiskResult(
                                False,
                                f"Price {order.price} not aligned to tick size {tick}",
                            )
                except Exception as exc:
                    return RiskResult(
                        allowed=False,
                        reason=f"Instrument lookup failed for {order.symbol}: {exc}",
                    )

            capital = self._capital_provider.get_available_balance()
            if capital <= 0:
                return RiskResult(False, "Insufficient capital")

            # F&O margin check (derivative segments only)
            if self._config.enable_margin_check and is_derivative_segment(order.exchange):
                margin_result = self._margin_checker.check(order)
                if not margin_result.allowed:
                    return margin_result

            # Effective notional: never treat bare quantity as rupee notional.
            ref_price, mult, instrument = self._margin_checker.resolve_market_context(order)
            price_for_notional = order.price.to_decimal() if hasattr(order.price, 'to_decimal') else Decimal(str(order.price))
            notional = effective_notional(
                order.quantity,
                price_for_notional,
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

            # Per-symbol concentration (includes in-flight pending — R4)
            current = self._position_manager.get_position(order.symbol, order.exchange)
            current_notional = (
                Decimal(str(abs(int(current.quantity))))
                * (current.avg_price.to_decimal() if hasattr(current.avg_price, "to_decimal") else Decimal(str(current.avg_price)))
                * (current.multiplier if getattr(current, "multiplier", None) else Decimal("1"))
                if current
                else Decimal("0")
            )
            pending_symbol = self._margin_checker.pending_symbol_notional(
                order.symbol, order.exchange
            )
            if (current_notional + pending_symbol + notional) / capital * 100 > self._config.max_position_pct:
                return RiskResult(False, f"Exceeds max position pct for {order.symbol}")

            # Gross exposure
            positions = self._position_manager.get_positions()
            gross = sum(
                (
                    Decimal(str(abs(int(p.quantity))))
                    * (p.avg_price.to_decimal() if hasattr(p.avg_price, "to_decimal") else Decimal(str(p.avg_price)))
                    * (p.multiplier if getattr(p, "multiplier", None) else Decimal("1"))
                )
                for p in positions
            )
            pending_gross = self._margin_checker.pending_gross()
            if (gross + pending_gross + notional) / capital * 100 > self._config.max_gross_exposure_pct:
                return RiskResult(False, "Exceeds max gross exposure pct")

            # Daily loss
            if self._daily_pnl_tracker.is_stale():
                self._daily_pnl_tracker.reset()
            if (
                self._daily_pnl_tracker.value < 0
                and abs(self._daily_pnl_tracker.value) / capital * 100
                >= self._config.max_daily_loss_pct
            ):
                return RiskResult(False, "Daily loss limit reached")

            self._margin_checker.reserve_pending(order, notional)
            return RiskResult(True)

    def update_daily_pnl(self, pnl: Decimal) -> None:
        """Update session equity delta (F5 — not absolute book MTM).

        ``pnl`` must be ``current_equity − session_open_equity``. Thread-safe.
        Also records the tick-to-tick change in the loss circuit breaker.
        """
        amount = Decimal(str(getattr(pnl, "amount", pnl)))
        with self._lock:
            self._daily_pnl_tracker.update(amount)

    def set_kill_switch(self, active: bool) -> None:
        """Enable or disable the kill switch by replacing the frozen config.

        Thread-safe. A concurrent ``check_order`` will see either the
        old config (kill switch as it was) or the new one (kill switch
        flipped), but never a torn read of the dataclass.
        """
        with self._lock:
            if active:
                self._kill_switch.activate()
            else:
                self._kill_switch.deactivate()
            # Keep RiskConfig.kill_switch in lock-step for snapshot/profile.
            self._config = self._config.replace(kill_switch=self._kill_switch.is_active())

    def is_kill_switch_active(self) -> bool:
        """Check if kill switch is currently active (freeze_all mode).

        When True, *all* order actions are blocked including exit_all /
        square-off. See :attr:`KILL_SWITCH_MODE`.

        Returns
        -------
        bool:
            True if kill switch prevents every order-modifying action.
        """
        with self._lock:
            return self._kill_switch.is_active()

    def reset_daily_pnl(self) -> None:
        """Reset the daily PnL to zero.

        Called by :class:`DailyPnlResetScheduler` at the configured
        rollover hour (default 00:00 IST). Safe to call manually from
        tests or operator scripts.

        Thread-safe. Increments ``_reset_count`` and records
        ``_last_reset_at`` so an SRE can confirm the rollover fired.
        """
        with self._lock:
            self._daily_pnl_tracker.reset()

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
            return self._daily_pnl_tracker.value

    @property
    def kill_switch(self) -> bool:
        """Current kill-switch state. Thread-safe.

        True if config kill switch is on **or** the optional domain KillSwitch
        is active (REF-4 bridge).
        """
        with self._lock:
            return self._kill_switch.is_active()

    @property
    def loss_circuit_breaker(self) -> LossCircuitBreaker:
        """Access the loss circuit breaker for inspection.

        B1: Read-only access to the circuit breaker. Callers should not
        mutate it directly; use :meth:`reset_loss_circuit_breaker`.
        """
        return self._loss_cb

    @property
    def trading_state(self) -> TradingState:
        """Access the trading state FSM for inspection and state transitions."""
        return self._trading_state

    @property
    def throttler(self) -> Throttler:
        """Access the submit/modify rate throttler for inspection."""
        return self._throttler

    @property
    def capital_provider(self):
        """Public accessor for capital provider (used by OrderPlacer)."""
        return self._capital_provider

    def snapshot(self) -> dict:
        """Return a JSON-serializable view of risk-manager state.

        Useful for ``/healthz`` and SRE dashboards. Locks are taken
        only briefly to read the scalar fields.
        """
        import time as _time

        with self._lock:
            base = {
                "kill_switch": self._kill_switch.is_active(),
                "daily_pnl": str(self._daily_pnl_tracker.value),
                "max_daily_loss_pct": str(self._config.max_daily_loss_pct),
                "max_position_pct": str(self._config.max_position_pct),
                "max_gross_exposure_pct": str(self._config.max_gross_exposure_pct),
                "reset_count": self._daily_pnl_tracker.reset_count,
                "kill_switch_toggles": self._kill_switch.toggles,
                "trading_state": self._trading_state.state.value,
                "last_reset_at": self._daily_pnl_tracker.last_reset_at,
                "seconds_since_last_reset": (
                    _time.time() - self._daily_pnl_tracker.last_reset_at
                    if self._daily_pnl_tracker.last_reset_at > 0
                    else None
                ),
            }

        # Append loss circuit breaker state (takes its own lock).
        base["loss_circuit_breaker"] = self._loss_cb.snapshot()
        return base

    def get_risk_profile(self) -> "RiskProfile":
        """Return a read-only domain.portfolio.risk_profile.RiskProfile snapshot.

        Implements domain.ports.risk_view.RiskViewPort so Session/AccountView
        can expose ``.risk_profile`` without importing this module. Additive
        and read-only: does not change any risk decision.
        """
        from domain.portfolio.risk_profile import RiskProfile

        with self._lock:
            config = self._config
            daily_pnl = self._daily_pnl_tracker.value
        capital = self._capital_provider.get_available_balance()
        return RiskProfile(
            max_daily_loss_pct=config.max_daily_loss_pct,
            max_position_pct=config.max_position_pct,
            max_gross_exposure_pct=config.max_gross_exposure_pct,
            kill_switch=config.kill_switch,
            daily_pnl=daily_pnl,
            capital=capital,
        )
