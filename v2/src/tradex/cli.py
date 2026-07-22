"""tradex CLI — stdlib argparse (no click)."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Sequence

from tradex import __version__


def _cmd_version(_args: argparse.Namespace) -> int:
    print(f"tradex {__version__}")
    return 0


def _cmd_config_validate(args: argparse.Namespace) -> int:
    from config.loader import load_config

    root = Path(args.config_dir)
    cfg = load_config(root, profile=args.profile)
    print(f"ok environment={cfg.environment.value} broker={cfg.broker}")
    return 0


def _cmd_scanner(args: argparse.Namespace) -> int:
    # ponytail: stub until analytics suite lands; try import then "ok"
    name = args.name
    try:
        from application.analytics import scanner  # type: ignore[attr-defined]

        result = getattr(scanner, name, None)
        if callable(result):
            print(result())
            return 0
        print(f"scanner {name}: {scanner!r}")
    except ImportError:
        print("ok")
    return 0


def _cmd_paper(_args: argparse.Namespace) -> int:
    print("paper trading session (stub)")
    return 0


def _cmd_backtest(_args: argparse.Namespace) -> int:
    print("backtest run (stub)")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="tradex")
    sub = parser.add_subparsers(dest="command")

    p_ver = sub.add_parser("version", help="print framework version")
    p_ver.set_defaults(func=_cmd_version)

    p_cfg = sub.add_parser("config", help="configuration")
    cfg_sub = p_cfg.add_subparsers(dest="config_cmd", required=True)
    p_val = cfg_sub.add_parser("validate", help="validate profile config")
    p_val.add_argument("--profile", default="paper")
    p_val.add_argument(
        "--config-dir",
        default=str(Path(__file__).resolve().parents[2] / "config"),
    )
    p_val.set_defaults(func=_cmd_config_validate)

    p_scan = sub.add_parser("scanner", help="run scanner")
    p_scan.add_argument("name", help="scanner name (e.g. momentum)")
    p_scan.set_defaults(func=_cmd_scanner)

    p_paper = sub.add_parser("paper", help="paper trading session")
    p_paper.set_defaults(func=_cmd_paper)

    p_bt = sub.add_parser("backtest", help="run backtest")
    p_bt.set_defaults(func=_cmd_backtest)

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
