"""Back-compat re-export — prefer :mod:`interface.api.bootstrap`.

Kept so existing ``from runtime.api_bootstrap import initialize_api_services``
call sites keep working. New code should import from interface.
"""

from __future__ import annotations

from interface.api.bootstrap import initialize_api_services

__all__ = ["initialize_api_services"]
