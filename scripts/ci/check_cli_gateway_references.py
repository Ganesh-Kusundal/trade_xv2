#!/usr/bin/env python3
"""CLI order/market modules must reference broker/OMS surfaces (static gate).

Replaces tests/integration/capability/test_cli_gateway_calls.py.
Scans ``src/interface/ui/commands`` (canonical CLI home after package move).
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
COMMANDS = ROOT / "src" / "interface" / "ui" / "commands"

_BROKER_TOUCHING = (
    "market_handlers.py",
    "market.py",
    "portfolio.py",
    "account.py",
    "order_placement.py",
    "oms.py",
    "risk_controls.py",
    "news.py",
    "search.py",
)

_EXPECTED = (
    "gw.quote",
    "gw.depth",
    "gw.history",
    "gw.portfolio",
    "gw.orders",
    "gw.market_data",
    "gw.options",
    "gw.futures",
    "gw.stream",
    "gw.modify_order",
    "gateway.",
    "active_broker",
    "broker_service",
    "broker_ops",
    "OmsService",
    "execution_service",
    "ExecutionComposer",
    "execution_composer",
    "composer.",
    "get_execution_composer",
    "place_order",
    "order_manager",
)


def main() -> int:
    violations: list[str] = []
    for name in _BROKER_TOUCHING:
        path = COMMANDS / name
        if not path.is_file():
            violations.append(f"missing module: {path.relative_to(ROOT).as_posix()}")
            continue
        text = path.read_text(encoding="utf-8")
        if not any(pat in text for pat in _EXPECTED):
            violations.append(path.relative_to(ROOT).as_posix())

    order_path = COMMANDS / "order_placement.py"
    if order_path.is_file():
        source = order_path.read_text(encoding="utf-8")
        if "modify_order" in source and "gw.modify_order" in source:
            if "composer.modify_order" not in source and "ExecutionComposer" not in source:
                violations.append(
                    "order_placement.py: modify_order must use composer, not gw.modify_order"
                )
        if not ("OmsService" in source or "execution_service" in source or "place_order" in source):
            violations.append("order_placement.py: place path must reference OMS/composer")

    if violations:
        print(
            "Broker-touching CLI modules missing OMS/broker references:\n"
            + "\n".join(violations),
            file=sys.stderr,
        )
        return 1
    print(f"OK: {len(_BROKER_TOUCHING)} broker-touching CLI modules wired")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
