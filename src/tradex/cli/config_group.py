"""``tradex config`` — CLI-only preferences (not AppConfig).

See ``brokers/cli/_preferences.py`` for what this does and does not manage.
"""

from __future__ import annotations

import click

from brokers.cli._preferences import PreferencesStore


@click.group()
@click.pass_context
def config(ctx: click.Context) -> None:
    """Manage tradex CLI preferences (broker.default, output.format)."""
    ctx.ensure_object(dict)
    ctx.obj.setdefault("prefs_store", PreferencesStore())


@config.command("list")
@click.pass_context
def list_cmd(ctx: click.Context) -> None:
    """Show all CLI preferences."""
    store: PreferencesStore = ctx.obj["prefs_store"]
    for key, value in store.load().as_dict().items():
        click.echo(f"{key}={value}")


@config.command("get")
@click.argument("key")
@click.pass_context
def get_cmd(ctx: click.Context, key: str) -> None:
    """Print the value of KEY (e.g. broker.default)."""
    store: PreferencesStore = ctx.obj["prefs_store"]
    try:
        click.echo(store.get(key))
    except KeyError as exc:
        raise click.ClickException(str(exc)) from exc


@config.command("set")
@click.argument("key")
@click.argument("value")
@click.pass_context
def set_cmd(ctx: click.Context, key: str, value: str) -> None:
    """Set KEY to VALUE."""
    store: PreferencesStore = ctx.obj["prefs_store"]
    try:
        prefs = store.set(key, value)
    except KeyError as exc:
        raise click.ClickException(str(exc)) from exc
    click.echo(f"{key}={prefs.get(key)}")


@config.command("edit")
@click.pass_context
def edit_cmd(ctx: click.Context) -> None:
    """Open the preferences file in $EDITOR."""
    store: PreferencesStore = ctx.obj["prefs_store"]
    if not store.path().exists():
        store.save(store.load())
    click.edit(filename=str(store.path()))


@config.command("reset")
@click.confirmation_option(prompt="Reset all CLI preferences to defaults?")
@click.pass_context
def reset_cmd(ctx: click.Context) -> None:
    """Reset preferences to defaults."""
    store: PreferencesStore = ctx.obj["prefs_store"]
    store.reset()
    click.echo("Preferences reset.")
