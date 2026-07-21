#!/usr/bin/env python3
"""CLI order/market modules must reference broker/OMS surfaces (static gate)."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
COMMANDS = ROOT / "src" / "interface" / "ui" / "commands"

# Modules that touch broker or OMS surfaces (not pure analytics/research).
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
    "extended_orders.py",
    "websocket.py",
)

_EXPECTED = (
    "broker_ops",
    "broker_service",
    "active_broker",
    "OmsService",
    "ExecutionComposer",
    "execution_composer",
    "composer.",
    "place_order",
    "order_manager",
    "get_execution_composer",
)


_COMPOSER_HELPERS = ROOT / "src" / "interface" / "ui" / "composer_helpers.py"

_BOOTSTRAP_PATTERNS = (
    "bootstrap_gateway",
    "require_gateway",
    "connect_live",
    "wrap_market_gateway",
)


def main() -> int:
    violations: list[str] = []
    if _COMPOSER_HELPERS.is_file():
        text = _COMPOSER_HELPERS.read_text(encoding="utf-8")
        if not any(pat in text for pat in _BOOTSTRAP_PATTERNS):
            violations.append(
                _COMPOSER_HELPERS.relative_to(ROOT).as_posix()
                + " must use bootstrap_gateway/wrap_market_gateway"
            )
        if "from_env" in text or "DhanBroker(" in text:
            violations.append(
                _COMPOSER_HELPERS.relative_to(ROOT).as_posix()
                + " must not construct raw wire (from_env/DhanBroker())"
            )
    for name in _BROKER_TOUCHING:
        path = COMMANDS / name
        if not path.is_file():
            violations.append(f"missing module: {name}")
            continue
        text = path.read_text(encoding="utf-8")
        if not any(pat in text for pat in _EXPECTED):
            violations.append(path.relative_to(ROOT).as_posix())
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
    sys.exit(main())
