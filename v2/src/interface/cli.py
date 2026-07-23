"""Interface CLI — commands organized by research questions."""

from __future__ import annotations

import argparse
import sys
from typing import Sequence


def _cmd_version(_args: argparse.Namespace) -> int:
    print("tradex 0.1.0")
    return 0


def _cmd_replay(args: argparse.Namespace) -> int:
    print(f"Replaying data from {args.data}")
    if args.from_date:
        print(f"  from: {args.from_date}")
    if args.to_date:
        print(f"  to:   {args.to_date}")
    print("  status: ready")
    return 0


def _cmd_backtest(args: argparse.Namespace) -> int:
    if args.strategy == "buy_and_hold":
        print(f"Backtest: strategy={args.strategy}, data={args.data}")
        print("  pipeline: FeaturePipeline")
        print("  engine:   StrategyEngine (1 strategy registered)")
    else:
        print(f"Unknown strategy: {args.strategy}")
        return 1
    return 0


def _cmd_paper(args: argparse.Namespace) -> int:
    print(f"Paper trading session: account={args.account}")
    print("  status: ready")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="tradex")
    sub = parser.add_subparsers(dest="command")

    p_ver = sub.add_parser("version", help="print framework version")
    p_ver.set_defaults(func=_cmd_version)

    p_replay = sub.add_parser("replay", help="replay historical data")
    p_replay.add_argument("--data", required=True, help="path to data file")
    p_replay.add_argument("--from", dest="from_date", default=None, help="start date")
    p_replay.add_argument("--to", dest="to_date", default=None, help="end date")
    p_replay.set_defaults(func=_cmd_replay)

    p_bt = sub.add_parser("backtest", help="run backtest")
    p_bt.add_argument("--strategy", default="buy_and_hold", help="strategy name")
    p_bt.add_argument("--data", required=True, help="path to data file")
    p_bt.set_defaults(func=_cmd_backtest)

    p_paper = sub.add_parser("paper", help="paper trading session")
    p_paper.add_argument("--account", required=True, help="account ID")
    p_paper.set_defaults(func=_cmd_paper)

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)
    if not getattr(args, "command", None):
        parser.print_help()
        return 0
    func = getattr(args, "func", None)
    if func is None:
        parser.print_help()
        return 0
    return int(func(args))


if __name__ == "__main__":
    sys.exit(main())
