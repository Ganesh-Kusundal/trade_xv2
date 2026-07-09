"""TradeXV2 Brokers Package — adapter implementations (transport layer).

**Product API (preferred)** — use the object model, not gateway classes::

    import tradex
    session = tradex.connect("paper")  # or "dhan" / "upstox" with process OMS
    reliance = session.universe.equity("RELIANCE")
    reliance.quote
    session.buy(reliance, 10)

**Transport (ops / legacy)** — concrete gateways live in broker packages::

    from brokers.dhan.gateway import DhanBrokerGateway
    from brokers.upstox.gateway import UpstoxBrokerGateway
    from brokers.paper import PaperGateway

Import Direction Rule
---------------------
    domain.ports → protocols (DataProvider, ExecutionProvider, BrokerAdapter)
    tradex.runtime → platform kernel
    brokers.dhan / upstox / paper → broker-specific adapters only
    brokers.common → residual shared contracts/capabilities (no re-export shims)

Never import broker-specific types from ``brokers`` top-level.
See ``reports/BROKERS_EVOLUTION_PLAN.md``.
"""

from __future__ import annotations

# Ensure ``src/`` is on sys.path so ``import domain`` resolves (src-layout).
import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parent.parent / "src"
if _SRC.is_dir() and str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

__all__: list[str] = []
