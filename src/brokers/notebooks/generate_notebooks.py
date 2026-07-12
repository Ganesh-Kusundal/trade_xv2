#!/usr/bin/env python3
"""Generate executable broker tutorial notebooks (01–19)."""

from __future__ import annotations

import json
from pathlib import Path

NOTEBOOKS = [
    ("01_authentication", "Connect and inspect session status"),
    ("02_search_instrument", "Resolve RELIANCE to instrument id"),
    ("03_get_quote", "Fetch a quote"),
    ("04_historical", "Fetch historical bars"),
    ("05_live_stream", "Subscribe to live data"),
    ("06_market_depth", "Fetch market depth"),
    ("07_option_chain", "Fetch NIFTY option chain"),
    ("08_orders", "List orders"),
    ("09_portfolio", "Show positions"),
    ("10_positions", "Show positions detail"),
    ("11_holdings", "Show holdings"),
    ("12_funds", "Show funds"),
    ("13_benchmark", "Run benchmark"),
    ("14_diagnostics", "Run diagnostics"),
    ("15_capability_discovery", "List capabilities"),
    ("16_mapping", "Run mapping certification"),
    ("17_error_handling", "Handle unknown symbol"),
    ("18_replay", "Historical replay probe"),
    ("19_performance", "Quote latency probe"),
]

CELLS = {
    "01_authentication": [
        "from brokers.session import BrokerSession\n\nsession = BrokerSession('paper')\nprint(session.broker_id, session.status)\nsession.close()",
    ],
    "02_search_instrument": [
        "from brokers.session import BrokerSession\n\nsession = BrokerSession('paper')\ninst = session.stock('RELIANCE')\nprint(inst.id)\nsession.close()",
    ],
    "03_get_quote": [
        "from brokers.session import BrokerSession\n\nsession = BrokerSession('paper')\nq = session.stock('RELIANCE').refresh()\nprint(q)\nsession.close()",
    ],
    "04_historical": [
        "from brokers.session import BrokerSession\n\nsession = BrokerSession('paper')\nseries = session.history(session.stock('RELIANCE'), timeframe='1D', days=5)\nprint(getattr(series, 'bar_count', 0))\nsession.close()",
    ],
    "05_live_stream": [
        "from brokers.session import BrokerSession\n\nsession = BrokerSession('paper')\ninst = session.stock('RELIANCE')\nh = session.subscribe(inst)\nprint('handle', h)\nsession.unsubscribe(inst)\nsession.close()",
    ],
    "06_market_depth": [
        "from brokers.session import BrokerSession\n\nsession = BrokerSession('paper')\nd = session.stock('RELIANCE').depth()\nprint(d)\nsession.close()",
    ],
    "07_option_chain": [
        "from brokers.session import BrokerSession\n\nsession = BrokerSession('paper')\nchain = session.option_chain('NIFTY')\nprint(len(getattr(chain, 'strikes', []) or []))\nsession.close()",
    ],
    "08_orders": [
        "from brokers.session import BrokerSession\n\nsession = BrokerSession('paper')\nprint(session.session.orders())\nsession.close()",
    ],
    "09_portfolio": [
        "from brokers.services import get_positions\nprint(get_positions('paper'))",
    ],
    "10_positions": [
        "from brokers.services import get_positions\nprint(get_positions('paper'))",
    ],
    "11_holdings": [
        "from brokers.services import get_holdings\nprint(get_holdings('paper'))",
    ],
    "12_funds": [
        "from brokers.services import get_funds\nprint(get_funds('paper'))",
    ],
    "13_benchmark": [
        "from brokers.services import run_benchmark\nrun_benchmark('paper').print_report()",
    ],
    "14_diagnostics": [
        "from brokers.services import run_diagnose\nrun_diagnose('paper').print_report()",
    ],
    "15_capability_discovery": [
        "from brokers.session import BrokerSession\n\nsession = BrokerSession('paper')\nprint(session.stock('RELIANCE').capabilities())\nsession.close()",
    ],
    "16_mapping": [
        "from brokers.certification.mapping import verify_mapping\nverify_mapping('paper').print_report()",
    ],
    "17_error_handling": [
        "from brokers.session import BrokerSession\n\nsession = BrokerSession('paper')\ntry:\n    session.stock('NOT_A_REAL_SYMBOL_XYZ')\nexcept Exception as e:\n    print(type(e).__name__, e)\nsession.close()",
    ],
    "18_replay": [
        "from brokers.session import BrokerSession\n\nsession = BrokerSession('paper')\nseries = session.history(session.stock('RELIANCE'), days=3)\nprint(getattr(series, 'bar_count', 0), 'bars')\nsession.close()",
    ],
    "19_performance": [
        "import time\nfrom brokers.session import BrokerSession\n\nsession = BrokerSession('paper')\nstart = time.perf_counter()\nsession.stock('RELIANCE').refresh()\nprint(f'quote latency: {(time.perf_counter()-start)*1000:.1f}ms')\nsession.close()",
    ],
}


def _notebook(cells: list[str]) -> dict:
    return {
        "cells": [
            {
                "cell_type": "code",
                "execution_count": None,
                "metadata": {},
                "outputs": [],
                "source": [line + "\n" for line in cell.split("\n")],
            }
            for cell in cells
        ],
        "metadata": {"kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"}},
        "nbformat": 4,
        "nbformat_minor": 5,
    }


def main() -> None:
    out = Path(__file__).resolve().parent
    out.mkdir(parents=True, exist_ok=True)
    for name, _title in NOTEBOOKS:
        nb = _notebook(CELLS.get(name, [f"# {name}\nprint('paper broker')"]))
        path = out / f"{name}.ipynb"
        path.write_text(json.dumps(nb, indent=1), encoding="utf-8")
        print("wrote", path)


if __name__ == "__main__":
    main()
