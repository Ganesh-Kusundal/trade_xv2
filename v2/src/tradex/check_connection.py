#!/usr/bin/env python3
"""Live broker connection check — authenticate + funds (no orders).

Probe-before-mint: reuses valid store/env JWT; never clears tokens to force TOTP.
On TotpRateLimitError: report remaining seconds and exit (no sleep/retry loop).

Usage (from v2/):
  PYTHONPATH=src python -m tradex.check_connection
  PYTHONPATH=src python -m tradex.check_connection --broker dhan
  PYTHONPATH=src python -m tradex.check_connection --broker upstox
"""

from __future__ import annotations

import argparse
import sys

from plugins.brokers.common.totp_cooldown import TotpRateLimitError
from plugins.brokers.dhan import DhanGateway
from plugins.brokers.dhan.config import DhanConfig
from plugins.brokers.upstox import UpstoxGateway
from plugins.brokers.upstox.config import UpstoxConfig
from shared.env import load_v2_env


def main(argv: list[str] | None = None) -> int:
    loaded = load_v2_env(override=True)
    parser = argparse.ArgumentParser(description="Check Dhan/Upstox live connectivity")
    parser.add_argument(
        "--broker",
        choices=("dhan", "upstox", "both"),
        default="both",
    )
    args = parser.parse_args(argv)

    print(f"env_file={loaded}")
    brokers = ["dhan", "upstox"] if args.broker == "both" else [args.broker]
    failed = 0
    for name in brokers:
        ok = _check(name)
        failed += 0 if ok else 1
    return 1 if failed else 0


def _check(name: str) -> bool:
    print(f"\n=== {name.upper()} ===")
    try:
        if name == "dhan":
            gw = DhanGateway(config=DhanConfig.from_env())
        else:
            gw = UpstoxGateway(config=UpstoxConfig.from_env())

        print(f"token_path={gw.connection.config.token_path}")
        print(f"cooldown_path={gw.connection.config.cooldown_path}")
        gw.connect()
        auth_ok = gw.authenticate()
        print(f"authenticate={auth_ok}")
        if not auth_ok:
            err = getattr(getattr(gw, "connection", None), "_last_auth_error", None)
            if isinstance(err, TotpRateLimitError):
                print(
                    f"BLOCKED: TOTP cooldown — retry in {err.remaining_seconds:.0f}s "
                    f"(do not poll; wait for broker window)"
                )
            else:
                print(f"FAIL: authenticate returned False ({err!r})")
            gw.close()
            return False
        funds = gw.get_funds()
        print(
            f"funds ok currency={funds.balance.currency} "
            f"balance={funds.balance.amount} equity={funds.equity.amount}"
        )
        positions = gw.get_positions()
        print(f"positions count={len(positions)}")
        gw.close()
        print("PASS")
        return True
    except Exception as exc:
        if isinstance(exc, TotpRateLimitError):
            print(
                f"BLOCKED: TOTP cooldown — retry in {exc.remaining_seconds:.0f}s "
                f"(do not poll; wait for broker window)"
            )
        else:
            print(f"FAIL: {type(exc).__name__}: {exc}")
        return False


if __name__ == "__main__":
    sys.exit(main())
