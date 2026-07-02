"""OMS persistence adapters.

.. deprecated::
    Canonical location is :mod:`infrastructure.persistence`.
    This package re-exports for backward compatibility.
"""

from infrastructure.persistence.sqlite_order_store import OmsWriterLockError, SqliteOrderStore

__all__ = ["OmsWriterLockError", "SqliteOrderStore"]
