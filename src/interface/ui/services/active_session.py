"""Single seam that builds a broker-bound ``tradex.Session`` for CLI commands.

Re-exports :mod:`application.portfolio.active_session` so existing UI imports
keep working. Canonical implementation lives in application (F9).
"""

from __future__ import annotations

from application.portfolio.active_session import get_active_session

__all__ = ["get_active_session"]
