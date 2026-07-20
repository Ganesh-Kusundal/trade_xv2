"""TradeX — institutional-grade algorithmic trading framework.

Product API (preferred)::

    import tradex
    from decimal import Decimal

    session = tradex.connect("paper")                 # mode=sim
    # session = tradex.connect("dhan", mode="market") # live data; buy disabled
    # session = tradex.connect("dhan", mode="trade")  # process OMS required
    stock = session.universe.equity("RELIANCE")
    stock.refresh()
    series = stock.history(timeframe="1D", days=5)       # history facade
    result = stock.buy(1, price=Decimal("2500"), correlation_id="demo:1")  # OMS-only
    # or: session.buy(stock, 1, price=Decimal("2500"))

    idx = session.universe.index("NIFTY")
    chain = idx.option_chain()
    if chain.atm:
        chain.atm.moneyness(chain.spot or Decimal("0"))

    session.close()

Do **not** import broker gateways for strategy code. Gateways under ``brokers/``
are transport only.

Docs: ``docs/OBJECT_MODEL.md`` · design: ``reports/OBJECT_MODEL_COMPLETION_DESIGN.md``
Safe-to-trade: ``reports/SAFE_TO_TRADE_GATE.md`` · example: ``examples/object_model_quickstart.py``
"""

from __future__ import annotations

# Ensure ``src/`` is on sys.path so ``import domain`` resolves without
# requiring PYTHONPATH=src (src-layout package).
import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parent.parent / "src"
if _SRC.is_dir() and str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from domain.instruments.asset_kind import AssetKind
from domain.instruments.instrument import (
    ETF,
    Commodity,
    Currency,
    Equity,
    Future,
    Index,
    Instrument,
    Option,
    Spot,
)
from domain.options.option_chain import OptionChain
from domain.universe import Session as DomainSession
from domain.universe import Universe
from tradex.session import connect, open_session

# Public factory — ``tradex.Session(broker="paper")`` / ``tradex.connect("paper")``
Session = open_session

# SM-20: The domain imports above are part of the public SDK surface.
# Users are expected to do: ``from tradex import Equity, OptionChain, ...``
# This is intentional, not an internal leak.  See docs/OBJECT_MODEL.md.

__all__ = [
    "ETF",
    "AssetKind",
    "Commodity",
    "Currency",
    "DomainSession",
    "Equity",
    "Future",
    "Index",
    "Instrument",
    "Option",
    "OptionChain",
    "Session",
    "Spot",
    "Universe",
    "connect",
    "open_session",
]
