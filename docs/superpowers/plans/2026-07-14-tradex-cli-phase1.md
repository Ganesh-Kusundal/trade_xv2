# TradeX Unified CLI — Phase 1 (Foundation) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stand up the architecturally-compliant foundation of the `git`/`kubectl`-style `tradex` CLI — a real `tradex.cli` package, layered output modes (human/json/yaml/quiet), a CLI-only preferences store, and the broker-identity commands (`list`/`current`/`switch`/`status`) that everything else in the full CLI spec builds on.

**Architecture:** New code is placed using the codebase's own documented boundaries (`context/architecture.md` System Boundaries table): `src/tradex/` already owns "Public package + CLI + session wiring", so the new `tradex config` group and the package restructure live there. `src/brokers/cli/broker.py` is already documented as "Thin front-end over `brokers.services`" for developer/CI/AI use — new identity commands (`list`/`current`/`switch`/`status`) are appended to it in the same style as its ~30 existing commands, not relocated. The new `CliPreferences` store lives in `src/brokers/cli/_preferences.py` (private, underscore-prefixed, matching `_render.py`/`_errors.py` convention) because that's where its only two consumers — `broker.py`'s new commands and `tradex/cli/config_group.py` — both need it; the dependency direction (`tradex.cli` → `brokers.cli`) is identical to the direction that already exists today (`tradex/cli.py` already imports `brokers.cli.broker`), so no new import cycle or layering violation is introduced. No `AppConfig`/`.env.*` code is touched — the new preferences store is explicitly CLI-only UX state (default broker, output format), not runtime/credential config (preserves G4 "single config source").

**Tech Stack:** Click (existing dep), Rich (existing dep, via `brokers/cli/_render.py`), PyYAML (existing dep — confirmed `PyYAML>=6.0` in `pyproject.toml`, importable as `yaml`). No new third-party dependencies.

## Global Constraints

- No new dependencies. Click's built-in `click.Choice`, `click.prompt`, `click.confirm`, `click.confirmation_option`, and `click.edit` cover every interactive-wizard need in this phase — do not add Prompt Toolkit/InquirerPy/Typer.
- `tradex config` operates ONLY on the new CLI preferences file (`~/.tradex/cli.json` by default, override via `TRADEX_CLI_CONFIG_PATH` env var for tests). It must never read or write `AppConfig` (`src/config/schema.py`) or any `.env.*` file — those remain the single source of truth for credentials/runtime config per `context/architecture.md` G4.
- New commands in `src/brokers/cli/broker.py` follow the file's existing conventions: `@click.pass_context`, resolve the target broker via the existing `_bid(ctx)` helper, and use `@handle_cli_errors` for read-only/query commands (matches the majority pattern already in that file — `connect`/`discover`/`quote`/`positions`/etc. all use it).
- All rendering goes through the existing `present()`/`console` machinery in `src/brokers/cli/_render.py` — do not build a second output pipeline. Extend `present()` for `--yaml`/`--quiet`; do not duplicate its dict/list/table dispatch logic.
- Every new/changed test uses `@pytest.mark.unit` (matches `tests/unit/tradex/test_cli.py` and `tests/unit/brokers/cli/test_cli_render.py`). Tests that monkeypatch a thin CLI display function (e.g. `get_quote`) are an already-accepted pattern in this file (see `test_cli_json_flag_emits_json`) — this is presentation-layer test isolation, not the "no real-money mocks" invariant (`architecture.md` §7.8), which concerns integration tests of actual broker/OMS behavior.
- No fabricated data. If a spec-mockup field (e.g. "Rate Limit Remaining", "Account" column) has no real accessor in the codebase yet, omit it and leave a `ponytail:` comment naming what's missing — do not hardcode a placeholder value.
- Run `ruff`/`mypy` clean and `graphify update .` before the final commit (per `context/ai-workflow-rules.md` §7–8).

## Explicitly Out of Scope for This Plan (tracked, not forgotten)

These are real parts of the original CLI spec that need their own plan once Phase 1 lands — do not pull them into this plan's tasks:

- `tradex order place/cancel/modify`, `tradex position list`, `tradex portfolio`, `tradex account` — per the real-money-safety decision, these must route live orders through the full OMS (`tradex.connect(..., mode="trade")` → `RiskGate` → idempotency), not the thin `brokers.services.place_order` path `broker order` uses today. That is materially more wiring (session lifecycle, error mapping from `ConnectError`) and deserves its own plan + review.
- `tradex broker add/remove/login/logout/token show|refresh|revoke` — no existing broker-agnostic accessor exposes a gateway's `AuthManager` (grepped `src/brokers/dhan/`, `src/brokers/upstox/`: no `gateway.auth_manager`-style accessor exists). Needs a small prep task per broker adapter before a CLI can safely show/refresh/revoke tokens.
- `tradex broker instruments sync/download/verify/stats/clear-cache/search`, `tradex broker rate-limit`, `tradex broker disconnect`, `tradex doctor` (top-level), interactive `broker add`/`login` wizards, the bare `tradex broker` dashboard TUI.
- `--table` output flag — the human-mode default already renders tabular data (`_render_records`) as Rich tables; a dedicated `--table` flag would be a no-op today. Add it only when a command's default view is *not* already tabular and needs a table override.

## File Structure

```
src/brokers/cli/
  _preferences.py         (NEW) CliPreferences dataclass + PreferencesStore (JSON file)
  _render.py               (MODIFY) present()/json_mode() gain yaml_mode()/quiet_mode()
  broker.py                (MODIFY) group gains --yaml/--quiet; new list/current/switch/status commands

src/tradex/
  cli.py                   (DELETE) — replaced by the package below
  cli/__init__.py           (NEW) re-exports `tradex` group
  cli/app.py                 (NEW) moved content of old cli.py, + mounts config group
  cli/config_group.py        (NEW) `tradex config` Click group (list/get/set/edit/reset)

tests/unit/brokers/cli/
  test_preferences.py       (NEW)
  test_broker_commands.py   (NEW) list/current/switch/status
  test_cli_render.py         (MODIFY) + yaml/quiet flag tests

tests/unit/tradex/
  test_cli.py                (MODIFY) + config-group-visible-in-help assertion
  test_cli_config.py        (NEW) config list/get/set/edit/reset via CliRunner

context/progress-tracker.md (MODIFY) — log this phase, name deferred Phase 2 scope
```

---

### Task 1: CLI preferences store

**Files:**
- Create: `src/brokers/cli/_preferences.py`
- Test: `tests/unit/brokers/cli/test_preferences.py`

**Interfaces:**
- Produces: `CliPreferences` frozen dataclass with fields `broker_default: str = "paper"`, `output_format: str = "human"`, methods `.get(key: str) -> str` and `.with_set(key: str, value: str) -> CliPreferences` (raise `KeyError` for unknown keys), `.as_dict() -> dict[str, str]` (keys `"broker.default"`, `"output.format"`).
- Produces: `PreferencesStore(path: Path | None = None)` — resolves path as: explicit `path` arg → else `TRADEX_CLI_CONFIG_PATH` env var → else `Path.home() / ".tradex" / "cli.json"`. Methods: `.load() -> CliPreferences`, `.save(prefs: CliPreferences) -> None`, `.get(key: str) -> str`, `.set(key: str, value: str) -> CliPreferences`, `.reset() -> CliPreferences`, `.path() -> Path`.

- [ ] **Step 1: Write the failing tests**

```python
"""Unit tests for the CLI-only preferences store (not AppConfig)."""

from __future__ import annotations

import pytest

from brokers.cli._preferences import CliPreferences, PreferencesStore


@pytest.mark.unit
def test_load_missing_file_returns_defaults(tmp_path) -> None:
    store = PreferencesStore(path=tmp_path / "cli.json")
    assert store.load() == CliPreferences(broker_default="paper", output_format="human")


@pytest.mark.unit
def test_set_then_get_round_trips(tmp_path) -> None:
    store = PreferencesStore(path=tmp_path / "cli.json")
    store.set("broker.default", "dhan")
    assert store.get("broker.default") == "dhan"
    assert store.load().broker_default == "dhan"


@pytest.mark.unit
def test_set_unknown_key_raises(tmp_path) -> None:
    store = PreferencesStore(path=tmp_path / "cli.json")
    with pytest.raises(KeyError):
        store.set("nope.nope", "x")


@pytest.mark.unit
def test_get_unknown_key_raises(tmp_path) -> None:
    store = PreferencesStore(path=tmp_path / "cli.json")
    with pytest.raises(KeyError):
        store.get("nope.nope")


@pytest.mark.unit
def test_reset_restores_defaults(tmp_path) -> None:
    store = PreferencesStore(path=tmp_path / "cli.json")
    store.set("broker.default", "upstox")
    store.reset()
    assert store.get("broker.default") == "paper"


@pytest.mark.unit
def test_save_creates_parent_directories(tmp_path) -> None:
    nested = tmp_path / "nested" / "dir" / "cli.json"
    store = PreferencesStore(path=nested)
    store.set("output.format", "json")
    assert nested.exists()


@pytest.mark.unit
def test_env_override_path(tmp_path, monkeypatch) -> None:
    target = tmp_path / "from_env.json"
    monkeypatch.setenv("TRADEX_CLI_CONFIG_PATH", str(target))
    store = PreferencesStore()
    store.set("broker.default", "dhan")
    assert target.exists()
    assert PreferencesStore().get("broker.default") == "dhan"


@pytest.mark.unit
def test_corrupt_file_falls_back_to_defaults(tmp_path) -> None:
    path = tmp_path / "cli.json"
    path.write_text("{not valid json")
    store = PreferencesStore(path=path)
    assert store.load() == CliPreferences()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/brokers/cli/test_preferences.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'brokers.cli._preferences'`

- [ ] **Step 3: Write the implementation**

```python
"""CLI-only preferences store — NOT the AppConfig runtime schema.

Holds CLI UX state only: which broker is the default target, preferred
output format. Broker credentials and everything AppConfig governs stay in
``.env.*`` / ``src/config/schema.py``; this module never reads or writes
those (keeps the single-config-source invariant, see context/architecture.md
G4).
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, replace
from pathlib import Path

_ENV_OVERRIDE = "TRADEX_CLI_CONFIG_PATH"
_DEFAULT_PATH = Path.home() / ".tradex" / "cli.json"

_KEY_FIELDS = {"broker.default": "broker_default", "output.format": "output_format"}


@dataclass(frozen=True)
class CliPreferences:
    broker_default: str = "paper"
    output_format: str = "human"

    def get(self, key: str) -> str:
        field = _KEY_FIELDS.get(key)
        if field is None:
            raise KeyError(f"unknown config key {key!r} (known: {sorted(_KEY_FIELDS)})")
        return getattr(self, field)

    def with_set(self, key: str, value: str) -> "CliPreferences":
        field = _KEY_FIELDS.get(key)
        if field is None:
            raise KeyError(f"unknown config key {key!r} (known: {sorted(_KEY_FIELDS)})")
        return replace(self, **{field: value})

    def as_dict(self) -> dict[str, str]:
        data = asdict(self)
        return {key: data[field] for key, field in _KEY_FIELDS.items()}


class PreferencesStore:
    """JSON-file-backed store for :class:`CliPreferences`."""

    def __init__(self, path: Path | None = None):
        if path is not None:
            self._path = path
        elif os.environ.get(_ENV_OVERRIDE):
            self._path = Path(os.environ[_ENV_OVERRIDE])
        else:
            self._path = _DEFAULT_PATH

    def path(self) -> Path:
        return self._path

    def load(self) -> CliPreferences:
        if not self._path.exists():
            return CliPreferences()
        try:
            data = json.loads(self._path.read_text())
        except (json.JSONDecodeError, OSError):
            return CliPreferences()
        return CliPreferences(
            broker_default=data.get("broker.default", "paper"),
            output_format=data.get("output.format", "human"),
        )

    def save(self, prefs: CliPreferences) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(json.dumps(prefs.as_dict(), indent=2))

    def get(self, key: str) -> str:
        return self.load().get(key)

    def set(self, key: str, value: str) -> CliPreferences:
        prefs = self.load().with_set(key, value)
        self.save(prefs)
        return prefs

    def reset(self) -> CliPreferences:
        prefs = CliPreferences()
        self.save(prefs)
        return prefs
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/brokers/cli/test_preferences.py -v`
Expected: PASS (8 tests)

- [ ] **Step 5: Commit**

```bash
git add src/brokers/cli/_preferences.py tests/unit/brokers/cli/test_preferences.py
git commit -m "feat(cli): add CLI-only preferences store (broker.default, output.format)"
```

---

### Task 2: Restructure `src/tradex/cli.py` into a package

Pure refactor — no behavior change. This unblocks Task 3 (`tradex config` needs a package to live in).

**Files:**
- Delete: `src/tradex/cli.py`
- Create: `src/tradex/cli/__init__.py`
- Create: `src/tradex/cli/app.py`
- Test: `tests/unit/tradex/test_cli.py` (existing — must keep passing unchanged)

**Interfaces:**
- Produces: `tradex.cli.app.tradex` — the Click group (same object identity/behavior as today's `tradex.cli.tradex`).
- Produces: `tradex.cli.tradex` — re-exported from `__init__.py` so `from tradex.cli import tradex` (used by the existing test file and the `pyproject.toml` `tradex = "tradex.cli:tradex"` entry point) keeps resolving.

- [ ] **Step 1: Confirm the current baseline is green**

Run: `pytest tests/unit/tradex/test_cli.py -v`
Expected: PASS (3 tests: `test_tradex_help_lists_subcommands`, `test_tradex_broker_help_shows_subcommands`, `test_tradex_version_option`)

- [ ] **Step 2: Create the package, moving the existing content into `app.py`**

`src/tradex/cli/app.py`:
```python
"""Unified ``tradex`` command — single facade over the OS CLIs.

This module is a thin dispatcher only. It does not reimplement any broker
or UI logic; it wires together the existing entry points:

* ``brokers.cli.broker:broker`` — the developer/CI/AI Click group.
* ``interface.ui.main:main`` — the rich/Textual terminal entrypoint.
* ``tradex.cli.config_group:config`` — CLI-only preferences (broker.default,
  output.format); see ``tradex/cli/config_group.py``.

Install the console script via ``[project.scripts] tradex = "tradex.cli:tradex"``.
"""

from __future__ import annotations

import importlib
import sys

import click

from brokers.cli.broker import broker as broker_group
from tradex.cli.config_group import config as config_group


@click.group()
@click.version_option(package_name="tradexv2")
def tradex() -> None:
    """TradeXV2 unified command — broker + UI surface."""


tradex.add_command(broker_group, name="broker")
tradex.add_command(config_group, name="config")


@tradex.command()
@click.argument("args", nargs=-1, type=click.UNPROCESSED)
def ui(args: tuple[str, ...]) -> None:
    """Launch the TradeXV2 rich/Textual terminal (interface.ui.main)."""
    # Loaded by string so the literal ``interface.ui`` import does not trip the
    # layer-isolation lint (TID251) — this facade is explicitly allowed to
    # dispatch into the UI layer.
    main = importlib.import_module("interface.ui.main").main

    # ``main()`` parses ``sys.argv[1:]`` directly, so strip the ``tradex ui``
    # prefix and leave only the arguments intended for the UI itself.
    sys.argv = [sys.argv[0], *args]
    main()


# ``version`` is exposed automatically via ``--version`` on the group; this
# explicit command keeps it discoverable in ``tradex --help``.


@tradex.command(name="version")
def _version() -> None:
    """Print the installed TradeXV2 version."""
    from importlib.metadata import version

    try:
        click.echo(version("tradexv2"))
    except Exception:  # pragma: no cover - package metadata edge cases
        click.echo("tradexv2 (version metadata unavailable)")
```

`src/tradex/cli/__init__.py`:
```python
"""tradex.cli — unified CLI package.

Re-exports the ``tradex`` Click group so ``tradex.cli:tradex`` (the
``[project.scripts]`` entry point in ``pyproject.toml``) and
``from tradex.cli import tradex`` both keep resolving after the
single-file-to-package restructure.
"""

from __future__ import annotations

from tradex.cli.app import tradex

__all__ = ["tradex"]
```

- [ ] **Step 3: Delete the old single-file module**

```bash
rm src/tradex/cli.py
```

(Task 3 creates `config_group.py` referenced above — until then `app.py` will fail to import. Do Steps 2 and 3 of Task 3 before running tests here, or stub `config_group.py` with an empty `@click.group() def config(): ...` temporarily. Simplest: do Task 3 first, then come back and delete `cli.py` / verify. Order the actual work as: Task 1 → Task 3's Step 3 implementation → Task 2's deletion+verification → Task 3's Steps 4-5 tests. The task numbering here reflects logical ownership, not strict execution order.)

- [ ] **Step 4: Run tests to verify nothing broke**

Run: `pytest tests/unit/tradex/test_cli.py -v`
Expected: PASS (same 3 tests, now served by the package)

Run: `python -c "import tradex.cli; print(tradex.cli.tradex)"`
Expected: prints the Click group repr, confirms `setuptools.packages.find` picked up the new subpackage without a `pyproject.toml` change.

- [ ] **Step 5: Commit**

```bash
git add src/tradex/cli/ tests/unit/tradex/test_cli.py
git rm src/tradex/cli.py
git commit -m "refactor(cli): split tradex/cli.py into a package (unblocks tradex config)"
```

---

### Task 3: `tradex config` command group

**Files:**
- Create: `src/tradex/cli/config_group.py`
- Test: `tests/unit/tradex/test_cli_config.py`

**Interfaces:**
- Consumes: `brokers.cli._preferences.PreferencesStore` (Task 1) — `.load()`, `.get(key)`, `.set(key, value)`, `.reset()`, `.path()`.
- Produces: `tradex.cli.config_group.config` — Click group with commands `list`, `get KEY`, `set KEY VALUE`, `edit`, `reset`. Mounted by `tradex/cli/app.py` (Task 2) as `tradex config`.

> Execution note: implement this task's Step 3 (the module below) *before* Task 2's Step 3 (deleting the old `cli.py`), since `app.py` imports `config_group` at module load time. Steps 1–2 and 4–5 of this task run after Task 2 is fully green.

- [ ] **Step 1: Write the failing tests**

```python
"""Tests for `tradex config` — CLI-only preferences, not AppConfig."""

from __future__ import annotations

import pytest
from click.testing import CliRunner

from tradex.cli import tradex


@pytest.fixture
def cli_config_env(tmp_path, monkeypatch):
    monkeypatch.setenv("TRADEX_CLI_CONFIG_PATH", str(tmp_path / "cli.json"))
    return tmp_path / "cli.json"


@pytest.mark.unit
def test_config_list_shows_defaults(cli_config_env) -> None:
    result = CliRunner().invoke(tradex, ["config", "list"])
    assert result.exit_code == 0, result.output
    assert "broker.default=paper" in result.output
    assert "output.format=human" in result.output


@pytest.mark.unit
def test_config_set_then_get(cli_config_env) -> None:
    runner = CliRunner()
    result = runner.invoke(tradex, ["config", "set", "broker.default", "dhan"])
    assert result.exit_code == 0, result.output
    result = runner.invoke(tradex, ["config", "get", "broker.default"])
    assert result.exit_code == 0, result.output
    assert result.output.strip() == "dhan"


@pytest.mark.unit
def test_config_set_unknown_key_fails(cli_config_env) -> None:
    result = CliRunner().invoke(tradex, ["config", "set", "nope.nope", "x"])
    assert result.exit_code != 0


@pytest.mark.unit
def test_config_get_unknown_key_fails(cli_config_env) -> None:
    result = CliRunner().invoke(tradex, ["config", "get", "nope.nope"])
    assert result.exit_code != 0


@pytest.mark.unit
def test_config_reset_prompts_and_restores_defaults(cli_config_env) -> None:
    runner = CliRunner()
    runner.invoke(tradex, ["config", "set", "broker.default", "upstox"])
    result = runner.invoke(tradex, ["config", "reset"], input="y\n")
    assert result.exit_code == 0, result.output
    result = runner.invoke(tradex, ["config", "get", "broker.default"])
    assert result.output.strip() == "paper"


@pytest.mark.unit
def test_config_reset_aborts_without_confirmation(cli_config_env) -> None:
    runner = CliRunner()
    runner.invoke(tradex, ["config", "set", "broker.default", "upstox"])
    result = runner.invoke(tradex, ["config", "reset"], input="n\n")
    assert result.exit_code != 0
    result = runner.invoke(tradex, ["config", "get", "broker.default"])
    assert result.output.strip() == "upstox"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/tradex/test_cli_config.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'tradex.cli.config_group'`

- [ ] **Step 3: Write the implementation**

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/tradex/test_cli_config.py tests/unit/tradex/test_cli.py -v`
Expected: PASS (6 new + 3 existing = 9 tests)

- [ ] **Step 5: Commit**

```bash
git add src/tradex/cli/config_group.py tests/unit/tradex/test_cli_config.py
git commit -m "feat(cli): add tradex config list/get/set/edit/reset"
```

---

### Task 4: `--yaml` / `--quiet` output modes

**Files:**
- Modify: `src/brokers/cli/_render.py`
- Modify: `src/brokers/cli/broker.py`
- Modify: `tests/unit/brokers/cli/test_cli_render.py`

**Interfaces:**
- Produces: `brokers.cli._render.yaml_mode(ctx) -> bool`, `brokers.cli._render.quiet_mode(ctx) -> bool` (same shape as the existing `json_mode(ctx) -> bool`).
- Modifies: `present(ctx, data, *, title=None, out=None)` — checks quiet first (no output), then yaml, then json (existing), then falls through to the existing Rich rendering.
- Modifies: `broker` group gains `--yaml`/`--quiet` (`-q`) flags alongside the existing `--broker`/`--json`, stored as `ctx.obj["yaml"]` / `ctx.obj["quiet"]`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/unit/brokers/cli/test_cli_render.py`:

```python
def test_cli_yaml_flag_emits_yaml(monkeypatch) -> None:
    import yaml

    monkeypatch.setattr(
        "brokers.cli.broker.get_quote",
        lambda b, symbol: {"symbol": symbol, "ltp": 123.0},
    )
    res = CliRunner().invoke(broker, ["--yaml", "--broker", "paper", "quote", "FOO"])
    assert res.exit_code == 0, res.output
    assert yaml.safe_load(res.output) == {"symbol": "FOO", "ltp": 123.0}


def test_cli_quiet_flag_suppresses_output() -> None:
    res = CliRunner().invoke(broker, ["--quiet", "--broker", "paper", "discover"])
    assert res.exit_code == 0, res.output
    assert res.output.strip() == ""


def test_cli_quiet_short_flag() -> None:
    res = CliRunner().invoke(broker, ["-q", "--broker", "paper", "discover"])
    assert res.exit_code == 0, res.output
    assert res.output.strip() == ""


def test_present_yaml_mode_direct() -> None:
    class _Ctx:
        obj = {"yaml": True}

    buf = StringIO()
    present(_Ctx(), {"a": 1, "b": "two"}, out=Console(file=buf, width=120))
    # yaml branch writes via logging (same channel present()'s json branch
    # already uses), not `out` — assert no exception and no Rich output on buf.
    assert buf.getvalue() == ""


def test_present_quiet_mode_direct() -> None:
    class _Ctx:
        obj = {"quiet": True}

    buf = StringIO()
    present(_Ctx(), {"a": 1}, out=Console(file=buf, width=120))
    assert buf.getvalue() == ""
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/brokers/cli/test_cli_render.py -v -k "yaml or quiet"`
Expected: FAIL — `broker` has no `--yaml`/`--quiet`/`-q` option (`click.exceptions.NoSuchOption` surfaces as non-zero `exit_code`).

- [ ] **Step 3: Write the implementation**

In `src/brokers/cli/_render.py`, add near `json_mode`:

```python
import yaml
```

(add to the existing top-of-file imports, alongside `import json`)

```python
def yaml_mode(ctx: Any | None = None) -> bool:
    """Return True when output should be YAML."""
    return bool(ctx is not None and getattr(ctx, "obj", None) and ctx.obj.get("yaml"))


def quiet_mode(ctx: Any | None = None) -> bool:
    """Return True when output should be suppressed entirely."""
    return bool(ctx is not None and getattr(ctx, "obj", None) and ctx.obj.get("quiet"))
```

Modify `present()`'s opening lines (everything after stays the same):

```python
def present(
    ctx: Any | None = None,
    data: Any = None,
    *,
    title: str | None = None,
    out: Console | None = None,
) -> None:
    """Render ``data`` as Rich (default), JSON, or YAML (machine modes)."""
    if quiet_mode(ctx):
        return
    target = out or console
    if yaml_mode(ctx):
        logger.info(yaml.safe_dump(safe_serialize(data), default_flow_style=False, sort_keys=False))
        return
    if json_mode(ctx):
        logger.info(json.dumps(safe_serialize(data), default=str, indent=2))
        return

    kind = _domain_type_name(data)
    # ... (rest of function unchanged)
```

In `src/brokers/cli/broker.py`, modify the group definition:

```python
@click.group()
@click.option("--broker", default="paper", help="Broker id (paper/dhan/upstox).")
@click.option("--json", "as_json", is_flag=True, help="Emit raw JSON instead of Rich tables.")
@click.option("--yaml", "as_yaml", is_flag=True, help="Emit YAML instead of Rich tables.")
@click.option("--quiet", "-q", "quiet", is_flag=True, help="Suppress output (exit code only).")
@click.pass_context
def broker(ctx: click.Context, broker: str, as_json: bool, as_yaml: bool, quiet: bool) -> None:
    """Trading OS broker developer CLI."""
    ctx.ensure_object(dict)
    ctx.obj["broker"] = broker
    ctx.obj["json"] = as_json
    ctx.obj["yaml"] = as_yaml
    ctx.obj["quiet"] = quiet
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/brokers/cli/test_cli_render.py -v`
Expected: PASS (all existing tests in the file plus the 5 new ones)

- [ ] **Step 5: Commit**

```bash
git add src/brokers/cli/_render.py src/brokers/cli/broker.py tests/unit/brokers/cli/test_cli_render.py
git commit -m "feat(cli): add --yaml and --quiet/-q output modes"
```

---

### Task 5: `tradex broker list`

**Files:**
- Modify: `src/brokers/cli/broker.py`
- Create: `tests/unit/brokers/cli/test_broker_commands.py`

**Interfaces:**
- Consumes: `available_brokers()` (already imported in `broker.py` from `brokers.session`), `BrokerSession`, `status_from_session` (already imported), `brokers.cli._preferences.PreferencesStore` (Task 1).
- Produces: `broker list` command — rows of `{"broker": str, "connected": bool, "active": bool}`, rendered via the existing `present()`.

- [ ] **Step 1: Write the failing test**

```python
"""Unit tests for the new `tradex broker` identity commands: list/current/switch/status."""

from __future__ import annotations

import json

import pytest
from click.testing import CliRunner

from brokers.cli.broker import broker


@pytest.fixture
def cli_config_env(tmp_path, monkeypatch):
    monkeypatch.setenv("TRADEX_CLI_CONFIG_PATH", str(tmp_path / "cli.json"))
    return tmp_path / "cli.json"


@pytest.mark.unit
def test_broker_list_includes_paper_connected(cli_config_env) -> None:
    result = CliRunner().invoke(broker, ["--json", "list"])
    assert result.exit_code == 0, result.output
    rows = json.loads(result.output)
    paper_rows = [r for r in rows if r["broker"] == "paper"]
    assert paper_rows, rows
    assert paper_rows[0]["connected"] is True
    assert paper_rows[0]["active"] is True  # paper is the default before any switch


@pytest.mark.unit
def test_broker_list_marks_configured_default_active(cli_config_env) -> None:
    from brokers.cli._preferences import PreferencesStore

    PreferencesStore().set("broker.default", "dhan")
    result = CliRunner().invoke(broker, ["--json", "list"])
    assert result.exit_code == 0, result.output
    rows = json.loads(result.output)
    by_id = {r["broker"]: r for r in rows}
    assert by_id["paper"]["active"] is False
    if "dhan" in by_id:
        assert by_id["dhan"]["active"] is True
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/brokers/cli/test_broker_commands.py -v`
Expected: FAIL — `list` is not a registered command on `broker` (`Error: No such command 'list'`).

- [ ] **Step 3: Write the implementation**

Append to `src/brokers/cli/broker.py` (after the existing `discover` command):

```python
@broker.command("list")
@click.pass_context
@handle_cli_errors
def list_cmd(ctx: click.Context) -> None:
    """List registered brokers with connection/active status.

    # ponytail: no broker-agnostic account-id accessor exists yet, so the
    # "Account" column from the original CLI spec mockup is omitted here —
    # add once brokers.services exposes one.
    """
    from brokers.cli._preferences import PreferencesStore

    default_broker = PreferencesStore().get("broker.default")
    rows: list[dict] = []
    for broker_id in available_brokers():
        connected = True
        if broker_id != "paper":
            try:
                s = BrokerSession(broker_id)
                try:
                    status_from_session(s)
                finally:
                    s.close()
            except Exception:
                connected = False
        rows.append(
            {"broker": broker_id, "connected": connected, "active": broker_id == default_broker}
        )
    present(ctx, rows, title="Brokers")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/brokers/cli/test_broker_commands.py -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
git add src/brokers/cli/broker.py tests/unit/brokers/cli/test_broker_commands.py
git commit -m "feat(cli): add tradex broker list"
```

---

### Task 6: `tradex broker current` and `tradex broker switch`

**Files:**
- Modify: `src/brokers/cli/broker.py`
- Modify: `tests/unit/brokers/cli/test_broker_commands.py`

**Interfaces:**
- Consumes: `brokers.cli._preferences.PreferencesStore` (Task 1), `available_brokers()`.
- Produces: `broker current` (prints `{"broker.default": <value>}`), `broker switch [BROKER_ID] [--yes/-y]` (interactive `click.Choice` picker when `BROKER_ID` omitted, `click.confirm` gate unless `--yes`).

- [ ] **Step 1: Write the failing tests**

Append to `tests/unit/brokers/cli/test_broker_commands.py`:

```python
@pytest.mark.unit
def test_broker_current_defaults_to_paper(cli_config_env) -> None:
    result = CliRunner().invoke(broker, ["--json", "current"])
    assert result.exit_code == 0, result.output
    assert json.loads(result.output) == {"broker.default": "paper"}


@pytest.mark.unit
def test_broker_switch_with_arg_and_yes_flag_persists(cli_config_env) -> None:
    from brokers.cli._preferences import PreferencesStore

    result = CliRunner().invoke(broker, ["switch", "paper", "--yes"])
    assert result.exit_code == 0, result.output
    assert PreferencesStore().get("broker.default") == "paper"


@pytest.mark.unit
def test_broker_switch_rejects_unknown_broker(cli_config_env) -> None:
    result = CliRunner().invoke(broker, ["switch", "not-a-real-broker", "--yes"])
    assert result.exit_code != 0


@pytest.mark.unit
def test_broker_switch_aborts_without_confirmation(cli_config_env) -> None:
    from brokers.cli._preferences import PreferencesStore

    PreferencesStore().set("broker.default", "paper")
    result = CliRunner().invoke(broker, ["switch", "paper"], input="n\n")
    assert result.exit_code == 0, result.output
    assert "Aborted" in result.output


@pytest.mark.unit
def test_broker_switch_interactive_prompts_for_choice(cli_config_env) -> None:
    from brokers.cli._preferences import PreferencesStore

    result = CliRunner().invoke(broker, ["switch"], input="paper\ny\n")
    assert result.exit_code == 0, result.output
    assert PreferencesStore().get("broker.default") == "paper"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/brokers/cli/test_broker_commands.py -v -k "current or switch"`
Expected: FAIL — `current`/`switch` are not registered commands.

- [ ] **Step 3: Write the implementation**

Append to `src/brokers/cli/broker.py`:

```python
@broker.command()
@click.pass_context
@handle_cli_errors
def current(ctx: click.Context) -> None:
    """Show the configured default broker."""
    from brokers.cli._preferences import PreferencesStore

    present(ctx, {"broker.default": PreferencesStore().get("broker.default")}, title="Current broker")


@broker.command()
@click.argument("broker_id", required=False)
@click.option("--yes", "-y", is_flag=True, help="Skip the confirmation prompt.")
@click.pass_context
def switch(ctx: click.Context, broker_id: str | None, yes: bool) -> None:
    """Switch the default broker (interactive picker if BROKER_ID is omitted)."""
    from brokers.cli._preferences import PreferencesStore

    choices = available_brokers()
    if broker_id is None:
        broker_id = click.prompt("Switch to", type=click.Choice(choices))
    elif broker_id not in choices:
        raise click.ClickException(f"unknown broker {broker_id!r} (known: {sorted(choices)})")

    if not yes and not click.confirm(f"Switch default broker to {broker_id!r}?"):
        click.echo("Aborted.")
        return

    PreferencesStore().set("broker.default", broker_id)
    present(ctx, {"broker.default": broker_id}, title="Switched")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/brokers/cli/test_broker_commands.py -v`
Expected: PASS (7 tests total in the file)

- [ ] **Step 5: Commit**

```bash
git add src/brokers/cli/broker.py tests/unit/brokers/cli/test_broker_commands.py
git commit -m "feat(cli): add tradex broker current and tradex broker switch"
```

---

### Task 7: `tradex broker status`

**Files:**
- Modify: `src/brokers/cli/broker.py`
- Modify: `tests/unit/brokers/cli/test_broker_commands.py`

**Interfaces:**
- Consumes: `_bid(ctx)` (existing helper), `BrokerSession`, `status_from_session`, `extensions_from_session` (all already imported in `broker.py`).
- Produces: `broker status` command — combines `status_from_session()`'s real fields (`broker_id`, `mode`, `orders_enabled`, `authenticated`, `instruments_loaded`, `connected`, `checkpoints`) with the session's capability `extensions` list, in one dict, rendered via `present()`.

Note: the original CLI-spec mockup for `status` also shows "REST Healthy", "Websocket Connected", and "Rate Limit Remaining" rows. Those require per-check granularity (`broker health`, already implemented via `run_health` in `src/brokers/platform_ops.py`) and a live rate-limiter snapshot accessor (does not exist yet — `TokenBucketRateLimiter.available_tokens` exists but nothing wires a fresh CLI invocation's session to the live limiter instance). This task does not fabricate those rows; `status` reports what a session actually knows about itself, and `health` (unchanged, already shipped) remains the command for the checklist view.

- [ ] **Step 1: Write the failing test**

Append to `tests/unit/brokers/cli/test_broker_commands.py`:

```python
@pytest.mark.unit
def test_broker_status_paper(cli_config_env) -> None:
    result = CliRunner().invoke(broker, ["--broker", "paper", "--json", "status"])
    assert result.exit_code == 0, result.output
    info = json.loads(result.output)
    assert info["broker_id"] == "paper"
    assert info["connected"] is True
    assert "extensions" in info
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/brokers/cli/test_broker_commands.py -v -k status`
Expected: FAIL — `status` is not a registered command.

- [ ] **Step 3: Write the implementation**

Append to `src/brokers/cli/broker.py`:

```python
@broker.command()
@click.pass_context
@handle_cli_errors
def status(ctx: click.Context) -> None:
    """Show current session status and capability extensions for the broker."""
    s = BrokerSession(_bid(ctx))
    try:
        info = status_from_session(s)
        info["extensions"] = extensions_from_session(s)
    finally:
        s.close()
    present(ctx, info, title=f"Status — {info['broker_id']}")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/brokers/cli/test_broker_commands.py -v`
Expected: PASS (8 tests total in the file)

- [ ] **Step 5: Commit**

```bash
git add src/brokers/cli/broker.py tests/unit/brokers/cli/test_broker_commands.py
git commit -m "feat(cli): add tradex broker status"
```

---

### Task 8: Full verification, docs, graphify

**Files:**
- Modify: `context/progress-tracker.md`

- [ ] **Step 1: Run the full CLI-relevant test suite**

Run: `pytest tests/unit/brokers/cli/ tests/unit/tradex/ -v`
Expected: PASS, all tests (existing + new from Tasks 1–7).

- [ ] **Step 2: Run architecture tests to confirm no new import-linter/layering violation**

Run: `pytest tests/architecture/ -v`
Expected: PASS, same baseline as before this plan (no new failures — this plan added no cross-layer imports beyond the pre-existing `tradex.cli → brokers.cli` direction).

- [ ] **Step 3: Lint/type-check**

Run: `ruff check src/brokers/cli/ src/tradex/cli/`
Expected: clean (fix any findings before continuing).

Run: `mypy src/brokers/cli/_preferences.py src/tradex/cli/config_group.py src/tradex/cli/app.py`
Expected: clean (fix any findings before continuing).

- [ ] **Step 4: Manual smoke test of the built CLI**

```bash
pip install -e . --no-deps -q 2>&1 | tail -5   # only if the package isn't already editable-installed
tradex --help
tradex config list
tradex config set broker.default paper
tradex broker list
tradex broker current
tradex broker status --broker paper
```

Expected: every command runs without traceback and prints sensible output; `tradex --help` lists `broker`, `config`, `ui`, `version`.

- [ ] **Step 5: Update `context/progress-tracker.md`**

Add a new entry under `## Completed`, above the most recent existing entry:

```markdown
### TradeX Unified CLI — Phase 1 Foundation (2026-07-14)

- Restructured `src/tradex/cli.py` → `src/tradex/cli/` package (`app.py` +
  `config_group.py`), zero behavior change to existing `tradex broker`/`tradex ui`.
- New CLI-only preferences store: `brokers/cli/_preferences.py`
  (`CliPreferences`/`PreferencesStore`, JSON file at `~/.tradex/cli.json`,
  override via `TRADEX_CLI_CONFIG_PATH`). Explicitly separate from `AppConfig`
  — does not touch `.env.*` or `src/config/schema.py` (preserves G4).
- New commands: `tradex config list/get/set/edit/reset`; `tradex broker
  list/current/switch/status` (appended to the existing `brokers/cli/broker.py`
  flat command registry, same conventions as its ~30 existing commands).
- New output modes: `--yaml` and `--quiet`/`-q` on the `broker` group,
  alongside the existing `--json` (`brokers/cli/_render.py::present()`).
- Architectural placement decision (recorded so it isn't re-litigated): new
  CLI-only concerns live in `src/tradex/` (already documented in
  `context/architecture.md`'s System Boundaries table as owning "Public
  package + CLI + session wiring"); the existing developer/CI/AI `broker`
  CLI stays in `src/brokers/cli/` unchanged. No relocation into
  `src/interface/`, no new `runtime/cli_compose.py` — avoided per
  project-overview.md's "evolutionary refactoring, no rewrite" principle.
- Explicitly deferred (tracked, not forgotten — see the plan's "Explicitly
  Out of Scope" section): `tradex order/position/portfolio/account` (must
  route live orders through the full OMS via `tradex.connect(mode="trade")`,
  not the thin `brokers.services.place_order` path `broker order` already
  uses — that existing thin path is a known pre-existing real-money-safety
  gap, not something this phase introduced or fixed); `broker
  add/remove/login/logout/token` (no broker-agnostic `AuthManager` accessor
  exists yet on any gateway); `broker instruments sync/download/verify/
  stats/clear-cache/search`; `broker rate-limit`; top-level `tradex doctor`;
  interactive wizards beyond `click.Choice`/`click.confirm`.
- Tests: `tests/unit/brokers/cli/test_preferences.py` (8),
  `test_broker_commands.py` (8), `test_cli_render.py` (+5),
  `tests/unit/tradex/test_cli_config.py` (6). Architecture suite unaffected.
```

- [ ] **Step 6: Run graphify**

Run: `graphify update .`
Expected: completes, `graphify-out/` reflects the new/moved files.

- [ ] **Step 7: Final commit**

```bash
git add context/progress-tracker.md
git commit -m "docs: log tradex CLI Phase 1 completion, name deferred Phase 2 scope"
```
