"""Universe management — symbol list loading from DuckDB/CSV.

Thin re-export facade. The authoritative implementation and the
``UNIVERSE_FILES`` / ``_universe_cache`` state live in
:mod:`datalake.core.schema` so that ``datalake.schema.load_universe``
and ``datalake.core.load_universe`` share a single cache (REF-4).
"""

from __future__ import annotations

from datalake.core.schema import (
    UNIVERSE_DIR,
    UNIVERSE_FILES,
    _universe_cache,
    load_universe,
)

__all__ = ["UNIVERSE_DIR", "UNIVERSE_FILES", "_universe_cache", "load_universe"]
