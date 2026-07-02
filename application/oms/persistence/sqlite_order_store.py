"""Backward-compat re-export — canonical location is infrastructure.persistence.

.. deprecated::
    New code should import from :mod:`infrastructure.persistence.sqlite_order_store`
    or :mod:`infrastructure.persistence` directly.  This module re-exports all
    public names for backward compatibility.
"""

from __future__ import annotations

from infrastructure.persistence.sqlite_order_store import (
    OmsWriterLockError as OmsWriterLockError,
)
from infrastructure.persistence.sqlite_order_store import (
    SqliteOrderStore as SqliteOrderStore,
)
