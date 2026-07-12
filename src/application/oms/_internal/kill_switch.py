"""Kill-switch state with edge-triggered event publishing.

Extracted from :class:`~application.oms._internal.risk_manager.RiskManager`.
Owns the boolean kill-switch state (``freeze_all`` desk policy), keeps an
optional domain :class:`~domain.risk.policy.KillSwitch` in lock-step, and
publishes ``KILL_SWITCH_TOGGLED`` when the state actually flips.

This module must NOT import from ``risk_manager`` (no circular deps).
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Callable

from domain.events.types import EventType

from application.oms._internal.risk_types import RiskConfig

if TYPE_CHECKING:
    from domain.risk.policy import KillSwitch as DomainKillSwitch

logger = logging.getLogger(__name__)

#: Desk policy: kill switch freezes every order action (incl. exit_all).
KILL_SWITCH_MODE = "freeze_all"


class KillSwitch:
    """Thread-unsafe kill-switch state holder.

    The owning :class:`~application.oms._internal.risk_manager.RiskManager`
    is responsible for serialising access under its lock; this class only
    stores the boolean and performs the side effects (domain bridge + event).
    """

    def __init__(
        self,
        config: RiskConfig,
        domain_kill_switch: "DomainKillSwitch | None" = None,
        on_risk_event: Callable[[str, dict], None] | None = None,
    ) -> None:
        self._config = config
        self._domain_kill_switch = domain_kill_switch
        self._on_risk_event = on_risk_event
        self._toggles: int = 0

    # -- State --

    def is_active(self) -> bool:
        """True if the kill switch prevents every order-modifying action.

        Includes the optional domain KillSwitch (REF-4 bridge).
        """
        if self._config.kill_switch:
            return True
        if self._domain_kill_switch is not None and self._domain_kill_switch.is_active:
            return True
        return False

    @property
    def state(self) -> bool:
        """Current kill-switch state (mirror of :meth:`is_active`)."""
        return self.is_active()

    @property
    def toggles(self) -> int:
        """Count of state flips since construction."""
        return self._toggles

    # -- Mutators --

    def activate(self) -> None:
        """Activate the kill switch (freeze_all)."""
        self._set(True)

    def deactivate(self) -> None:
        """Deactivate the kill switch."""
        self._set(False)

    def _set(self, active: bool) -> None:
        previous = self._config.kill_switch
        self._config = self._config.replace(kill_switch=active)
        # Keep optional domain KillSwitch in lock-step with config.
        if self._domain_kill_switch is not None:
            if active:
                self._domain_kill_switch.activate()
            else:
                self._domain_kill_switch.deactivate()
        if previous != active:
            self._toggles += 1
            logger.warning(
                "kill_switch_toggled",
                extra={"new_state": active, "previous": previous},
            )
            if self._on_risk_event is not None:
                self._on_risk_event(
                    EventType.KILL_SWITCH_TOGGLED.value,
                    {"active": active, "previous": previous},
                )
