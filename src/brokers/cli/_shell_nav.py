"""Hierarchical numbered menu navigation for the broker shell."""

from __future__ import annotations

import json
import logging
import shlex
import sys
from typing import Any

import click
from rich.prompt import Prompt
from rich.rule import Rule
from rich.table import Table

logger = logging.getLogger(__name__)

from brokers.cli._render import console, json_mode
from brokers.cli._shell_types import (
    Back,
    EnterSection,
    Help,
    Quit,
    ResolvedAction,
    RetryConnect,
    RunCommand,
    ShellItem,
    ShellMenu,
    Unknown,
)

# Re-export types for backward compatibility.
__all__ = [
    "RECOVERY_MENU",
    "Back",
    "EnterSection",
    "Help",
    "Quit",
    "ResolvedAction",
    "RetryConnect",
    "RunCommand",
    "ShellItem",
    "ShellMenu",
    "Unknown",
    "arg_hint_display",
    "ask_menu_line",
    "build_main_menu",
    "click_command_name",
    "command_needs_args",
    "commands_needing_args",
    "filter_extension_commands",
    "print_unknown",
    "prompt_for_args",
    "render_help_for_menu",
    "render_menu",
    "resolve_input",
]
from brokers.cli._shell_ui import render_header
from domain.ports.broker_id import BrokerId
from infrastructure.adapter_factory import get_broker_extension_classes

_SECTION_DEFS: list[tuple[str, list[str]]] = [
    ("Session", ["connect", "discover", "capability", "symbols", "instrument", "mappings"]),
    ("Market", ["quote", "history", "subscribe", "depth", "option_chain"]),
    (
        "Diagnostics",
        ["diagnose", "health", "doctor", "benchmark", "market_hours", "certify", "verify"],
    ),
]


# Shell prompt defaults for required positional args (Click has no default for those).
_DEFAULT_SYMBOLS: dict[str, str] = {
    "quote": "RELIANCE",
    "history": "RELIANCE",
    "subscribe": "RELIANCE",
    "depth": "RELIANCE",
    "depth20": "RELIANCE",
    "depth200": "RELIANCE",
    "depth30": "RELIANCE",
    "instrument": "RELIANCE",
    "symbols": "RELIANCE",
    "option_chain": "NIFTY",
    "news": "RELIANCE",
}

# CLI command name → runtime extension capability name.
_EXTENSION_ALIASES: dict[str, str] = {
    "depth20": "depth_20",
    "depth200": "depth_200",
    "depth30": "depth_30",
    "news": "news",
}

# Reverse of _EXTENSION_ALIASES: runtime capability name → CLI command name.
_RUNTIME_TO_CLI: dict[str, str] = {v: k for k, v in _EXTENSION_ALIASES.items()}


def _cli_name_for_extension(cls: type) -> str:
    """Derive CLI command name from an Extension class.

    Reads the runtime ``name`` property from a bare instance and maps it back
    to the CLI name via ``_RUNTIME_TO_CLI``.
    """
    # G1: capability-driven dispatch
    try:
        obj: Any = object.__new__(cls)
        runtime_name: str = obj.name
        return _RUNTIME_TO_CLI.get(runtime_name, runtime_name)
    except (AttributeError, TypeError):
        pass
    name = cls.__name__
    if name.endswith("Extension"):
        name = name[: -len("Extension")]
    for i, ch in enumerate(name):
        if ch.islower():
            name = name[i:]
            break
    return name.lower()


_FOOTER_HINTS = "number · name · exit/back · help · quit/q"
_RECOVERY_FOOTER = "1 retry · 2 doctor · q quit"


def click_command_name(group: Any, name: str) -> str | None:
    """Map shell menu name to registered Click command (underscore ↔ hyphen)."""
    if name in group.commands:
        return name
    alt = name.replace("_", "-")
    if alt in group.commands:
        return alt
    return None


def _extension_runtime_key(cli_name: str) -> str:
    return _EXTENSION_ALIASES.get(cli_name, cli_name)


def _click_arg_hint(group: Any, command: str) -> str | None:
    """Build arg hint from Click command params (no hand-maintained drift)."""
    cmd_name = click_command_name(group, command)
    if cmd_name is None:
        return None
    cmd = group.commands.get(cmd_name)
    if cmd is None:
        return None
    parts: list[str] = []
    for param in cmd.params:
        if isinstance(param, click.Argument):
            parts.append(param.name.upper().replace("_", " "))
        elif isinstance(param, click.Option) and param.required:
            parts.append(f"--{param.name}")
    return " ".join(parts) if parts else None


def command_needs_args(group: Any, command: str) -> bool:
    """True when the Click command has required positional args or options."""
    cmd_name = click_command_name(group, command)
    if cmd_name is None:
        return False
    cmd = group.commands.get(cmd_name)
    if cmd is None:
        return False
    return any(param.required for param in cmd.params)


def commands_needing_args(group: Any) -> frozenset[str]:
    return frozenset(name for name in group.commands if command_needs_args(group, name))


def arg_hint_display(group: Any, command: str) -> str | None:
    """Menu hint: default symbol when curated, else Click-derived labels."""
    default = _DEFAULT_SYMBOLS.get(command)
    if default:
        return default
    return _click_arg_hint(group, command)


def filter_extension_commands(broker_id: str, declared: list[str] | None) -> list[str]:
    """Return broker extension CLI commands, filtered by session capabilities."""
    # G1: capability-driven dispatch
    available = [_cli_name_for_extension(cls) for cls in get_broker_extension_classes(broker_id)]
    if not available:
        return []
    if not declared:
        return available
    norm = {str(d).lower() for d in declared}
    return [cmd for cmd in available if _extension_runtime_key(cmd) in norm or cmd in declared]


def _command_help(group: Any, name: str) -> str:
    cmd = group.commands.get(name)
    if cmd is None:
        return "—"
    text = (cmd.get_short_help_str() or cmd.help or "").strip()
    if not text and cmd.help:
        text = cmd.help.strip().splitlines()[0]
    return text or "—"


def _build_section_menu(section: str, commands: list[str], group: Any) -> ShellMenu:
    items = [
        ShellItem(
            i + 1,
            cmd,
            _command_help(group, cmd),
            kind="command",
            arg_hint=arg_hint_display(group, cmd),
        )
        for i, cmd in enumerate(commands)
    ]
    return ShellMenu(title=section, items=items)


def build_main_menu(
    group: Any,
    broker_id: str = "paper",
    *,
    declared_extensions: list[str] | None = None,
) -> ShellMenu:
    sections = list(_SECTION_DEFS)
    ext_cmds = filter_extension_commands(broker_id, declared_extensions)
    if ext_cmds:
        sections.append(("Extensions", ext_cmds))
    items = [
        ShellItem(
            i + 1,
            section,
            f"Enter {section} commands",
            kind="section",
            child=_build_section_menu(section, commands, group),
        )
        for i, (section, commands) in enumerate(sections)
    ]
    return ShellMenu(title="Main", items=items, is_main=True)


RECOVERY_MENU = ShellMenu(
    title="Recovery",
    is_recovery=True,
    items=[
        ShellItem(1, "retry", "Retry broker connect", kind="retry"),
        ShellItem(2, "doctor", "Run environment pre-flight", kind="command"),
        ShellItem(3, "quit", "Leave shell", kind="quit"),
    ],
)


def _item_by_number(menu: ShellMenu, num: int) -> ShellItem | None:
    for item in menu.items:
        if item.number == num:
            return item
    return None


def _item_by_name(menu: ShellMenu, name: str) -> ShellItem | None:
    key = name.lower().replace("-", "_")
    for item in menu.items:
        if item.name.lower() == key:
            return item
    return None


def resolve_input(line: str, menu: ShellMenu, group: Any) -> ResolvedAction:
    stripped = line.strip()
    if not stripped:
        return Unknown("")
    low = stripped.lower()
    if low in {"quit", "q"}:
        return Quit()
    if low in {"exit", "back"}:
        return Back()
    if low == "help":
        return Help()
    try:
        tokens = shlex.split(stripped)
    except ValueError:
        return Unknown(stripped)
    if not tokens:
        return Unknown(stripped)

    if menu.is_recovery:
        if tokens[0] in {"1", "retry"}:
            return RetryConnect()
        if tokens[0] in {"2", "doctor"}:
            return RunCommand("doctor", tokens[1:])
        if tokens[0] in {"3", "quit", "q"}:
            return Quit()
        return Unknown(tokens[0])

    first = tokens[0].lower()
    rest = tokens[1:]

    if first.isdigit():
        item = _item_by_number(menu, int(first))
        if item is None:
            return Unknown(first)
        if item.kind == "section" and item.child:
            return EnterSection(item.child)
        if item.kind == "command":
            return RunCommand(item.name, rest)
        return Unknown(first)

    item = _item_by_name(menu, first)
    if item:
        if item.kind == "section" and item.child:
            return EnterSection(item.child)
        if item.kind == "command":
            return RunCommand(item.name, rest)

    if menu.is_main:
        for item in menu.items:
            if item.kind == "section" and item.name.lower() == first and item.child:
                return EnterSection(item.child)

    if first in group.commands or click_command_name(group, first):
        return RunCommand(first, rest)

    return Unknown(first)


def prompt_for_args(command: str, arg_hint: str | None) -> list[str]:
    default = _DEFAULT_SYMBOLS.get(command, "")
    label = arg_hint or "value"
    if default:
        label = f"{label} [{default}]"
    if sys.stdin.isatty() and sys.stdout.isatty():
        raw = Prompt.ask(f"[yellow]{label}[/yellow]", default=default)
    else:
        raw = input(f"{label}: ") or default
    return shlex.split(raw) if raw.strip() else ([default] if default else [])


def _prompt_label(broker_id: str, menu: ShellMenu) -> str:
    """Prompt label without square brackets (Rich eats [dhan] as markup)."""
    if menu.is_recovery:
        return f"broker({broker_id}:recovery)"
    if menu.is_main:
        return f"broker({broker_id})"
    return f"broker({broker_id}:{menu.title})"


def ask_menu_line(broker_id: str, menu: ShellMenu) -> str:
    label = _prompt_label(broker_id, menu)
    return input(f"{label}> ")


def _recovery_hint(broker_id: str, session_info: dict[str, Any]) -> str:
    """Context-aware recovery guidance from the actual connect failure."""
    err = (session_info.get("error") or "").lower()
    remediation = (session_info.get("remediation") or "").lower()
    combined = f"{err} {remediation}"

    if "2 minutes" in combined or "rate limit" in combined or "cooldown" in combined:
        return (
            "[yellow]Fix:[/yellow] Dhan TOTP rate limit — wait [bold]2 minutes[/bold], "
            "then press [green]1[/green] to remint, or paste a fresh token into .env.local."
        )
    # G1: capability-driven dispatch
    if "dh-906" in combined or "token rejected" in combined or "expired" in combined:
        if broker_id == BrokerId.DHAN:
            return (
                "[yellow]Fix:[/yellow] Token rejected by Dhan — credentials exist but need refresh. "
                "Wait 2 min, press [green]1[/green] to remint via TOTP, or update DHAN_ACCESS_TOKEN in .env.local."
            )
        if broker_id == BrokerId.UPSTOX:
            return (
                "[yellow]Fix:[/yellow] Token rejected — refresh UPSTOX_ACCESS_TOKEN in .env.local, "
                "then press [green]1[/green]."
            )
    if broker_id == BrokerId.UPSTOX and (
        "423" in combined or "locked" in combined or "maintenance" in combined
    ):
        return (
            "[yellow]Fix:[/yellow] Upstox funds API is in overnight maintenance "
            "(12:00 AM–5:30 AM IST). Auth may already be fine — retry after "
            "[bold]5:30 AM IST[/bold], or press [green]1[/green] then."
        )
    if broker_id == BrokerId.DHAN:
        return (
            "[yellow]Fix:[/yellow] set DHAN_ACCESS_TOKEN or TOTP credentials in .env.local, "
            "then press [green]1[/green] to retry."
        )
    if broker_id == BrokerId.UPSTOX:
        return (
            "[yellow]Fix:[/yellow] set UPSTOX_ACCESS_TOKEN / OAuth credentials in .env.local, "
            "then press [green]1[/green] to retry."
        )
    return (
        "[yellow]Fix:[/yellow] check broker credentials in .env.local, "
        "then press [green]1[/green] to retry."
    )


def render_help_for_menu(
    broker_id: str,
    menu: ShellMenu,
    *,
    group: Any,
    out: Any | None = None,
) -> None:
    """Show command reference for the current menu without reconnecting."""
    target = out or console
    title = (
        "Recovery help"
        if menu.is_recovery
        else ("Main menu help" if menu.is_main else f"{menu.title} help")
    )
    table = Table(title=title, title_justify="left", show_header=True, header_style="bold")
    table.add_column("Command", style="bold green", width=18, no_wrap=True)
    table.add_column("Args", width=16)
    table.add_column("What it does", overflow="fold")
    for item in menu.items:
        if item.kind == "section":
            table.add_row(item.name, "—", item.help)
            continue
        hint = item.arg_hint or arg_hint_display(group, item.name) or "—"
        table.add_row(item.name, hint, item.help)
    target.print(table)
    target.print(f"[dim]{_RECOVERY_FOOTER if menu.is_recovery else _FOOTER_HINTS}[/dim]\n")


def render_menu(
    ctx: Any,
    broker_id: str,
    session_info: dict[str, Any],
    menu: ShellMenu,
    *,
    group: Any,
    out: Any | None = None,
) -> None:
    target = out or console
    if json_mode(ctx):
        payload = {
            "broker_id": broker_id,
            "session": session_info,
            "menu": menu.title,
            "items": [
                {"number": i.number, "name": i.name, "help": i.help, "kind": i.kind}
                for i in menu.items
            ],
            "hints": _RECOVERY_FOOTER if menu.is_recovery else _FOOTER_HINTS,
        }
        logger.info(json.dumps(payload, default=str, indent=2))
        return

    render_header(session_info, broker_id, out=target)

    title = "Recovery" if menu.is_recovery else ("Main menu" if menu.is_main else menu.title)
    table = Table(title=title, title_justify="left", show_header=True, header_style="bold")
    table.add_column("#", style="bold yellow", width=4, justify="right")
    table.add_column("Name", style="bold green", width=18, no_wrap=True)
    table.add_column("What it does", overflow="fold")
    for item in menu.items:
        hint = f" [dim]({item.arg_hint})[/dim]" if item.arg_hint else ""
        table.add_row(str(item.number), item.name + hint, item.help)
    target.print(table)

    if menu.is_recovery:
        target.print(_recovery_hint(broker_id, session_info))
        target.print(f"[dim]{_RECOVERY_FOOTER}[/dim]\n")
    elif menu.is_main:
        target.print(
            "[dim]Pick a section by number or name[/dim] (e.g. [green]2[/green] or [green]market[/green])"
        )
        target.print(Rule(style="dim"))
        target.print(f"[dim]{_FOOTER_HINTS}[/dim]\n")
    else:
        target.print(
            "[dim]Pick a command by number or name[/dim]; [green]exit[/green] returns to main menu"
        )
        target.print(Rule(style="dim"))
        target.print(f"[dim]{_FOOTER_HINTS}[/dim]\n")


def print_unknown(token: str, *, out: Any | None = None) -> None:
    if not token:
        return
    (out or console).print(f"[red]unknown choice:[/red] {token}")
