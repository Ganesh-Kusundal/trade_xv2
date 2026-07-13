"""Shell navigation types — dataclasses and type aliases."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal


@dataclass
class ShellItem:
    number: int
    name: str
    help: str
    kind: Literal["section", "command", "retry", "quit"] = "command"
    arg_hint: str | None = None
    child: ShellMenu | None = None


@dataclass
class ShellMenu:
    title: str
    items: list[ShellItem] = field(default_factory=list)
    is_main: bool = False
    is_recovery: bool = False


class Quit:
    pass


@dataclass
class Back:
    pass


@dataclass
class Help:
    pass


@dataclass
class RetryConnect:
    pass


@dataclass
class EnterSection:
    menu: ShellMenu


@dataclass
class RunCommand:
    name: str
    args: list[str]


@dataclass
class Unknown:
    token: str


ResolvedAction = Quit | Back | Help | RetryConnect | EnterSection | RunCommand | Unknown
