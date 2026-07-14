"""Unit tests for broker shell menu navigation."""

from __future__ import annotations

from brokers.cli._shell_nav import (
    Back,
    EnterSection,
    Help,
    Quit,
    RunCommand,
    RetryConnect,
    build_main_menu,
    resolve_input,
)
from brokers.cli.broker import broker


def test_resolve_main_enter_market_by_number() -> None:
    main = build_main_menu(broker, "paper")
    action = resolve_input("2", main, broker)
    assert isinstance(action, EnterSection)
    assert action.menu.title == "Market"


def test_resolve_main_enter_market_by_name() -> None:
    main = build_main_menu(broker, "paper")
    action = resolve_input("market", main, broker)
    assert isinstance(action, EnterSection)
    assert action.menu.title == "Market"


def test_resolve_section_run_quote() -> None:
    main = build_main_menu(broker, "paper")
    market = resolve_input("2", main, broker)
    assert isinstance(market, EnterSection)
    action = resolve_input("1 RELIANCE", market.menu, broker)
    assert isinstance(action, RunCommand)
    assert action.name == "quote"
    assert action.args == ["RELIANCE"]


def test_resolve_exit_is_back_not_quit() -> None:
    main = build_main_menu(broker, "paper")
    assert isinstance(resolve_input("exit", main, broker), Back)
    assert isinstance(resolve_input("quit", main, broker), Quit)


def test_resolve_global_command_on_main() -> None:
    main = build_main_menu(broker, "paper")
    action = resolve_input("discover", main, broker)
    assert isinstance(action, RunCommand)
    assert action.name == "discover"


def test_recovery_retry() -> None:
    from brokers.cli._shell_nav import RECOVERY_MENU

    assert isinstance(resolve_input("1", RECOVERY_MENU, broker), RetryConnect)


def test_prompt_label_includes_broker_id() -> None:
    from brokers.cli._shell_nav import RECOVERY_MENU, _prompt_label, build_main_menu

    assert _prompt_label("dhan", RECOVERY_MENU) == "broker(dhan:recovery)"
    assert _prompt_label("dhan", build_main_menu(broker, "dhan")) == "broker(dhan)"


def test_dhan_main_menu_includes_extensions() -> None:
    main = build_main_menu(broker, "dhan")
    names = [item.name for item in main.items]
    assert "Extensions" in names


def test_upstox_main_menu_extensions_includes_news() -> None:
    main = build_main_menu(broker, "upstox")
    section_names = [item.name for item in main.items]
    assert "Extensions" in section_names
    extensions = next(i.child for i in main.items if i.name == "Extensions")
    cmd_names = [item.name for item in extensions.items]
    assert "news" in cmd_names
    assert "depth30" in cmd_names


def test_upstox_filter_extension_commands_full_declared() -> None:
    from brokers.cli._shell_nav import filter_extension_commands

    cmds = filter_extension_commands("upstox", ["depth_30", "news"])
    assert cmds == ["depth30", "news"]


def test_upstox_filter_extension_commands_depth_only_hides_news() -> None:
    from brokers.cli._shell_nav import filter_extension_commands

    cmds = filter_extension_commands("upstox", ["depth_30"])
    assert cmds == ["depth30"]
    assert "news" not in cmds


def test_prompt_for_args_default_reliance(monkeypatch) -> None:
    from brokers.cli._shell_nav import prompt_for_args

    monkeypatch.setattr("sys.stdin.isatty", lambda: False)
    monkeypatch.setattr("sys.stdout.isatty", lambda: False)
    monkeypatch.setattr("builtins.input", lambda _: "")
    assert prompt_for_args("quote", "SYMBOL") == ["RELIANCE"]


def test_recovery_hint_token_rejected() -> None:
    from brokers.cli._shell_nav import _recovery_hint

    hint = _recovery_hint(
        "dhan",
        {
            "error": "Token rejected: DH-906 on GET /fundlimit",
            "remediation": "Token rejected or expired.",
        },
    )
    assert "rejected" in hint.lower()
    assert "DHAN_ACCESS_TOKEN" not in hint or "refresh" in hint.lower()


def test_recovery_hint_rate_limit() -> None:
    from brokers.cli._shell_nav import _recovery_hint

    hint = _recovery_hint(
        "dhan",
        {"error": "Token can be generated once every 2 minutes."},
    )
    assert "2 minutes" in hint


def test_recovery_hint_upstox_funds_maintenance() -> None:
    from brokers.cli._shell_nav import _recovery_hint

    hint = _recovery_hint(
        "upstox",
        {"error": "Upstox API GET ... failed: HTTP 423 Locked"},
    )
    assert "5:30" in hint
    assert "maintenance" in hint.lower()


def test_extension_alias_super_orders() -> None:
    from brokers.cli._shell_nav import filter_extension_commands

    # super_order/forever_order have no CLI alias since the analytics-first
    # pivot removed their Click commands; they surface under their raw
    # runtime name (no matching command, so the shell no-ops on selection).
    declared = ["depth_20", "depth_200", "super_order", "forever_order"]
    cmds = filter_extension_commands("dhan", declared)
    assert "super_order" in cmds
    assert "forever_order" in cmds
    assert "depth20" in cmds
    assert "depth200" in cmds


def test_extension_alias_hides_unsupported() -> None:
    from brokers.cli._shell_nav import filter_extension_commands

    cmds = filter_extension_commands("dhan", ["depth_20"])
    assert cmds == ["depth20"]
    assert "super_orders" not in cmds


def test_command_needs_args_from_click() -> None:
    from brokers.cli._shell_nav import command_needs_args

    assert command_needs_args(broker, "quote") is True
    assert command_needs_args(broker, "option_chain") is True
    assert command_needs_args(broker, "discover") is False
    assert command_needs_args(broker, "certify") is False


def test_click_command_name_resolves_hyphen_aliases() -> None:
    from brokers.cli._shell_nav import click_command_name

    assert click_command_name(broker, "option_chain") == "option-chain"
    assert click_command_name(broker, "market_hours") == "market-hours"
    assert click_command_name(broker, "quote") == "quote"


def test_resolve_section_run_option_chain_by_number() -> None:
    from brokers.cli._shell_nav import click_command_name

    main = build_main_menu(broker, "paper")
    market = resolve_input("2", main, broker)
    assert isinstance(market, EnterSection)
    action = resolve_input("5", market.menu, broker)
    assert isinstance(action, RunCommand)
    assert action.name == "option_chain"
    assert click_command_name(broker, action.name) == "option-chain"


def test_render_help_smoke() -> None:
    from brokers.cli._shell_nav import RECOVERY_MENU, build_main_menu, render_help_for_menu

    printed: list[str] = []

    class _Capture:
        def print(self, *args, **kwargs) -> None:
            printed.append(" ".join(str(a) for a in args))

    main = build_main_menu(broker, "paper")
    market = next(i.child for i in main.items if i.name == "Market")
    render_help_for_menu("paper", market, group=broker, out=_Capture())
    render_help_for_menu("dhan", RECOVERY_MENU, group=broker, out=_Capture())
    assert any("help" in line.lower() for line in printed)
    assert any("retry" in line.lower() or "number" in line.lower() for line in printed)
