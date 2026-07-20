"""TradeXV2 Brokers Package — Trading OS market-access layer.

**Public API (use this)**::

    from brokers.session import BrokerSession

    session = BrokerSession.connect("paper")  # or "dhan" / "upstox"
    stock = session.stock("RELIANCE")
    stock.refresh()

Or via CLI / MCP (same ``brokers.services`` core)::

    broker quote RELIANCE --broker paper
    broker verify paper

Gateways under ``brokers.dhan.wire`` / ``brokers.upstox.wire`` are
**private transport shims** — do not import them from product code.
See ``docs/constitution/09-broker-subsystem-gap-analysis.md``.
"""

from __future__ import annotations

from brokers._bootstrap import ensure_repo_src

ensure_repo_src()

# Ensure ``src/`` is on sys.path so ``import domain`` resolves (src-layout).
import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parent.parent / "src"
if _SRC.is_dir() and str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

__all__ = ["BrokerSession", "available_brokers", "create_session"]


def __getattr__(name: str):
    if name in __all__:
        from brokers import session as _session

        return getattr(_session, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
