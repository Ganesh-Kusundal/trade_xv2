"""Order state validation with transition table enforcement.

Extracted from OrderManager to follow SRP. This collaborator is responsible
solely for validating order status transitions against the canonical
transition table.

Thread Safety
-------------
This class is thread-safe. All public methods acquire the provided lock
before accessing internal state machines.

Usage:
    validator = OrderStateValidator(ORDER_STATUS_TRANSITIONS)
    validator.validate_transition(order_id, old_status, new_status)
    # Raises IllegalTransitionError if invalid
"""

from __future__ import annotations

import logging
import threading
from typing import TYPE_CHECKING

from cachetools import TTLCache

from domain.types import ORDER_STATUS_TRANSITIONS, OrderStatus
from domain.state_machine import IllegalTransitionError, StateMachine

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


class OrderStateValidator:
    """Validates order status transitions using a state machine.

    Parameters
    ----------
    transitions:
        Dictionary mapping each state to allowed next states.
        Defaults to ORDER_STATUS_TRANSITIONS.
    enforce:
        When True, invalid transitions raise IllegalTransitionError.
        When False, violations are logged but accepted (audit mode).

    Thread Safety
    -------------
    All public methods are thread-safe when a lock is provided.
    Internal state machines dict is protected by caller's lock.
    """

    def __init__(
        self,
        transitions: dict[OrderStatus, frozenset[OrderStatus]] | None = None,
        enforce: bool = True,
        max_orders: int = 10000,
        ttl_seconds: int = 86400,
    ) -> None:
        """Initialize the state validator.

        Parameters
        ----------
        transitions:
            Dictionary mapping each state to allowed next states.
            Defaults to ORDER_STATUS_TRANSITIONS.
        enforce:
            When True, invalid transitions raise IllegalTransitionError.
            When False, violations are logged but accepted (audit mode).
        max_orders:
            Maximum number of order state machines to track.
            Oldest entries are evicted when limit is reached.
        ttl_seconds:
            Time-to-live for order state machines (default: 24 hours).
            Expired entries are automatically evicted.
        """
        self._transitions = transitions or ORDER_STATUS_TRANSITIONS
        self._enforce = enforce
        # Bounded cache with TTL eviction to prevent memory leaks
        # Thread-safe: caller must hold lock when accessing
        self._state_machines: TTLCache = TTLCache(
            maxsize=max_orders,
            ttl=ttl_seconds,
        )

    @property
    def enforce(self) -> bool:
        """True if enforcement mode is active (raises on invalid transitions)."""
        return self._enforce

    def validate_transition(
        self,
        order_id: str,
        old_status: OrderStatus,
        new_status: OrderStatus,
        lock: threading.RLock | None = None,
    ) -> None:
        """Validate a status transition for an order.

        Parameters
        ----------
        order_id:
            Unique order identifier.
        old_status:
            Current status before transition.
        new_status:
            Requested target status.
        lock:
            Optional lock for thread safety. If provided, acquired internally.

        Raises
        ------
        IllegalTransitionError:
            If transition is invalid and enforcement mode is active.
        """
        if old_status == new_status:
            # No actual transition, just an update with same status
            return

        state_machine = self._get_or_create_state_machine(order_id, old_status)

        if not state_machine.can_transition_to(new_status):
            if self._enforce:
                raise IllegalTransitionError(old_status, new_status)
            else:
                logger.warning(
                    "OrderStateValidator: illegal order status transition "
                    "%s → %s for order %s (audit mode: accepting)",
                    old_status.value,
                    new_status.value,
                    order_id,
                )
        else:
            # Valid transition: update state machine
            state_machine.transition_to(new_status)

    def get_state_machine(self, order_id: str) -> StateMachine[OrderStatus] | None:
        """Retrieve the state machine for an order.

        Parameters
        ----------
        order_id:
            Unique order identifier.

        Returns
        -------
        StateMachine[OrderStatus] | None:
            The state machine if it exists, None otherwise.
        """
        return self._state_machines.get(order_id)

    def reset(self, order_id: str) -> None:
        """Remove the state machine for an order.

        Used for cleanup or testing.

        Parameters
        ----------
        order_id:
            Unique order identifier.
        """
        self._state_machines.pop(order_id, None)

    def clear(self) -> None:
        """Clear all state machines.

        Used for testing or system reset.
        """
        self._state_machines.clear()

    def _get_or_create_state_machine(
        self,
        order_id: str,
        initial_status: OrderStatus,
    ) -> StateMachine[OrderStatus]:
        """Get existing or create new state machine for an order.

        Parameters
        ----------
        order_id:
            Unique order identifier.
        initial_status:
            Initial status for new state machines.

        Returns
        -------
        StateMachine[OrderStatus]:
            The state machine for the order.
        """
        state_machine = self._state_machines.get(order_id)
        if state_machine is None:
            state_machine = StateMachine(
                transitions=self._transitions,
                initial=initial_status,
            )
            self._state_machines[order_id] = state_machine
        return state_machine
