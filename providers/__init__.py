"""Deprecated package (ENG-016).

Prefer::

    from brokers.dhan.transport import DhanOrderTransport
    from tradex.runtime.adapter_factory import create_data_adapter, create_execution_provider
"""

from __future__ import annotations

import warnings

warnings.warn(
    "providers package is deprecated; use brokers.* / tradex.runtime adapters (ENG-016).",
    DeprecationWarning,
    stacklevel=2,
)
