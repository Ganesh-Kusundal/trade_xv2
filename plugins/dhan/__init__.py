"""Dhan broker plugin — re-exports from brokers.dhan for backward compatibility.

The canonical broker implementation lives in ``brokers.dhan``. This plugin
module re-exports it so consumers can import from ``plugins.dhan`` (the
intended location per the FDOS target layout). Eventually ``brokers/dhan``
will be deleted and ``plugins/dhan`` will contain the implementation directly.
"""
from brokers.dhan import *  # noqa: F401,F403 — re-export everything
