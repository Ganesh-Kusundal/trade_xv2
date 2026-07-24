#!/usr/bin/env python3
"""Live Dhan data check via the gateway — index, equity, future, option.

Proves the InstrumentId -> wire (security_id/segment) mapping resolves to the
broker's own ids and that live market data comes back for each asset class.
Uses DhanGateway as the only standard interface (no direct HTTP / wire poking).

Usage (from v2/):
  env -u PYTHONPATH PYTHONPATH=src <venv>/bin/python ../scripts/verify/verify_dhan_live_data.py
"""

from __future__ import annotations

import sys

from domain.value_objects import InstrumentId
from plugins.brokers.dhan import DhanGateway
from plugins.brokers.dhan.config import DhanConfig
from shared.env import load_v2_env


def _nearest(by_id: dict, *, right: str | tuple[str, ...]) -> InstrumentId | None:
    """Nearest-expiry pure-NIFTY derivative. Canonical ids carry the full
    trading symbol as the underlying segment (e.g. NFO:NIFTY-JUL2026-FUT:…),
    so pure-NIFTY contracts are matched by the 'NFO:NIFTY-' value prefix."""
    rights = {right} if isinstance(right, str) else set(right)
    matches = [
        inst.instrument_id
        for inst in by_id.values()
        if inst.instrument_id.value.startswith("NFO:NIFTY-")
        and inst.instrument_id.expiry is not None
        and inst.instrument_id.right in rights
    ]
    if not matches:
        return None
    return min(matches, key=lambda iid: (iid.expiry, iid.strike or 0))


def main() -> int:
    load_v2_env(override=True)

    gw = DhanGateway(config=DhanConfig.from_env())
    gw.connect()
    if not gw.authenticate():
        print(f"FAIL authenticate: {getattr(gw.connection, '_last_auth_error', None)!r}")
        return 1
    print("PASS authenticate")

    gw.load_instruments()
    wire = gw.connection.wire
    by_id = gw.connection.instruments._by_id
    print(f"PASS load_instruments ({len(by_id)} instruments)")

    targets: list[tuple[str, InstrumentId | None]] = [
        ("index", InstrumentId.index("NSE", "NIFTY")),
        ("equity", InstrumentId.equity("NSE", "RELIANCE")),
        ("future", _nearest(by_id, right="FUT")),
        ("option", _nearest(by_id, right=("CE", "PE"))),
    ]

    failures = 0
    for label, iid in targets:
        if iid is None:
            failures += 1
            print(f"FAIL {label:7s} no matching NIFTY derivative in loaded master")
            continue
        try:
            sec = wire.security_id(iid)
            seg = wire.get_segment(iid)
            ltp = gw.ltp(iid)
            print(f"PASS {label:7s} {iid.value:42s} sec={sec:>8s} seg={seg:9s} ltp={ltp}")
        except Exception as exc:  # noqa: BLE001 — report, don't crash the sweep
            failures += 1
            print(f"FAIL {label:7s} {iid.value:42s} {type(exc).__name__}: {exc}")

    gw.close()
    print("\nRESULT:", "FAIL" if failures else "PASS")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
