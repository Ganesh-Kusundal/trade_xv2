"""Re-export ``AccountConnectionRegistry`` from its canonical infrastructure home.

The registry governs gateway lifecycle + auth-failure circuit breaking, so it
now lives in ``infrastructure.connection.account_registry``. Broker and runtime
callers keep importing through this facade.
"""

from __future__ import annotations

from infrastructure.connection.account_registry import AccountConnectionRegistry

__all__ = ["AccountConnectionRegistry"]
