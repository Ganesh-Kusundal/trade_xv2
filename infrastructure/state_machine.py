"""State machine — back-compat re-export.

The state machine is domain logic and now lives in :mod:`domain.state_machine`
(see D4 OMS→infra port extraction). This module re-exports the canonical
symbols so existing ``infrastructure.state_machine`` imports keep working.
"""

from domain.state_machine import IllegalTransitionError, StateMachine

__all__ = ["IllegalTransitionError", "StateMachine"]
