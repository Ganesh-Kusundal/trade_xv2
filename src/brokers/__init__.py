"""TradeXV2 Brokers Package — Trading OS market-access adapters.

**Public API (domain-centric)**::

    from brokers import BrokerSession

    session = BrokerSession.connect("paper")  # or "dhan" / "upstox"
    stock = session.stock("RELIANCE")
    stock.refresh()                          # market data on Instrument
    session.gateway.place_order(...)         # broker ops on Gateway
    session.gateway.subscribe([stock])
    session.extension(SomeExtension)         # broker-specific only

Wire adapters under ``brokers.providers.dhan.wire`` / ``brokers.providers.upstox.wire`` are
**private transport shims** — do not import them from product code.
See ``docs/superpowers/specs/2026-07-21-broker-hybrid-facade-design.md``.
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

__all__ = ["BrokerGateway", "BrokerSession", "available_brokers", "create_session"]


def __getattr__(name: str):
    if name == "BrokerGateway":
        from brokers.gateway import BrokerGateway

        return BrokerGateway
    if name in ("BrokerSession", "available_brokers", "create_session"):
        from brokers import session as _session

        return getattr(_session, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
