"""CLI-level error rendering — catches exceptions, shows Rich error panels."""

from __future__ import annotations

import functools
import logging
import sys
from typing import Any, TypeVar

import click
from rich.panel import Panel

from brokers.cli._render import console, json_mode

logger = logging.getLogger(__name__)

F = TypeVar("F", bound=click.Command)

_BROKER_ERRORS: tuple[type[Exception], ...] | None = None


class _BrokerErrorsState:
    """Module-level broker errors state (lazy singleton)."""

    _errors: tuple[type[Exception], ...] | None = None

    @classmethod
    def get(cls) -> tuple[type[Exception], ...]:
        if cls._errors is None:
            from brokers.exceptions import BrokerError
            from domain.exceptions import TradeXV2Error
            from brokers.services._session import LiveBrokerBlockedError
            cls._errors = (
                BrokerError,
                TradeXV2Error,
                LiveBrokerBlockedError,
                ConnectionError,
                TimeoutError,
                OSError,
            )
        return cls._errors


def _lazy_broker_errors() -> tuple[type[Exception], ...]:
    return _BrokerErrorsState.get()


def _render_error(exc: Exception) -> None:
    """Render an exception as a Rich error panel or JSON error object."""
    err_type = type(exc).__name__
    err_msg = str(exc)
    remediation = getattr(exc, "remediation", "") or ""

    if json_mode():
        import json as _json
        payload: dict[str, Any] = {"error": err_type, "message": err_msg}
        if remediation:
            payload["remediation"] = remediation
        logger.info(_json.dumps(payload, default=str))
        return

    parts = [f"[bold red]{err_type}[/bold red]"]
    if err_msg:
        parts.append(err_msg)
    if remediation:
        parts.append(f"\n[yellow]Remediation:[/yellow] {remediation}")

    console.print(Panel("\n".join(parts), title="Error", border_style="red"))


def handle_cli_errors(func: F) -> F:
    """Decorator for Click commands that catches broker/service exceptions.

    Renders a Rich error panel (or JSON in machine mode) instead of a raw
    traceback. Re-raises SystemExit, KeyboardInterrupt, and click.exceptions.Exit.
    """

    @functools.wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        try:
            return func(*args, **kwargs)
        except (click.exceptions.Exit, SystemExit, KeyboardInterrupt):
            raise
        except Exception as exc:
            # Only catch known broker/service errors; let unknown exceptions through
            if isinstance(exc, _lazy_broker_errors()):
                _render_error(exc)
                sys.exit(1)
            raise

    return wrapper  # type: ignore[return-value]
