# TradeX Unified CLI — Phase 2 (Positions, Portfolio, Orders) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `tradex position list`, `tradex portfolio`, and `tradex order place` — the three commands Phase 1 explicitly deferred because they touch real money and must route through the full OMS (`tradex.connect(mode=...)`), not the thin `brokers.services` path Phase 1's other commands use.

**Architecture:** New top-level Click groups (`position`, `portfolio`, `order`) live in `src/tradex/cli.py`, mounted alongside `broker`/`config`. They call `tradex.session.open_session()` (the public composition root, already used by `interface.api.routers.orders`) directly — not `brokers.services`, and not a new composition-root module. Read commands (`position list`, `portfolio`) use `mode="market"` (execution_provider only, no OMS, works for any broker including live — confirmed by tracing `open_session`: `executor` is built whenever a gateway exists, independent of `orders_wanted`). The order-placing command (`order place`) uses `mode="trade"` so it always routes through `OrderIntent → RiskGate → OrderManager`, closing the safety gap Phase 1 explicitly declined to extend.

**Tech Stack:** Same as Phase 1 (Click, Rich via `brokers.cli._render.present`). No new dependencies.

## Global Constraints

- Every session opened by these commands MUST be closed (`session.close()`) even on error — use try/finally, matching the existing `BrokerSession` close pattern in `brokers/cli/broker.py`.
- `order place` on a LIVE broker (`dhan`/`upstox`) requires an explicit confirmation prompt before submitting, unless `--yes`/`-y` is passed — matches the CLI spec's "Safe by default (confirmation for destructive actions)" principle. `paper` never prompts (matches `broker order`'s existing "paper-safe by default" convention).
- Reuse `present(ctx, data, title=...)` from `brokers.cli._render` for all output — same `--json`/`--yaml`/`--quiet` modes Phase 1 already wired onto the `broker` group; these new groups get their own copies of the same three flags (Click groups don't inherit sibling groups' options).
- `tradex.session.open_session` raises `domain.connect_errors.ConnectError` on any connect failure (auth/gateway/OMS) — catch it and render via the existing error-panel pattern in `brokers/cli/_errors.py::_render_error` (reuse, don't reimplement).
- Every new test uses `@pytest.mark.unit`.
- Do not implement `order cancel`/`order modify`/`account`/instruments/token/wizards in this plan — out of scope, name them in `context/progress-tracker.md` as still-deferred when this plan completes.

## File Structure

```
src/tradex/cli.py                        (MODIFY) add position/portfolio/order groups
tests/unit/tradex/test_cli_position.py   (NEW)
tests/unit/tradex/test_cli_portfolio.py  (NEW)
tests/unit/tradex/test_cli_order.py      (NEW)
```

---

### Task 1: `tradex position list`

**Files:**
- Modify: `src/tradex/cli.py`
- Test: `tests/unit/tradex/test_cli_position.py`

**Interfaces:**
- Consumes: `tradex.session.open_session(broker, mode="market")` → `DomainSession` with `.account.positions() -> list`, `.close()`.
- Produces: `tradex position list [--broker BROKER]` — `--broker` defaults to the same switched-preference default as the `broker` group (reuse `brokers.cli.broker._default_broker`).

- [ ] **Step 1: Write the failing test**

```python
"""Tests for `tradex position list`."""

from __future__ import annotations

import pytest
from click.testing import CliRunner

from tradex.cli import tradex


@pytest.mark.unit
def test_position_list_paper_runs_clean() -> None:
    result = CliRunner().invoke(tradex, ["position", "list", "--broker", "paper"])
    assert result.exit_code == 0, result.output


@pytest.mark.unit
def test_position_list_uses_switched_default_broker(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("TRADEX_CLI_CONFIG_PATH", str(tmp_path / "cli.json"))
    from brokers.cli._preferences import PreferencesStore

    PreferencesStore().set("broker.default", "paper")
    result = CliRunner().invoke(tradex, ["position", "list"])
    assert result.exit_code == 0, result.output
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/tradex/test_cli_position.py -v`
Expected: FAIL — `Error: No such command 'position'` (group doesn't exist yet).

- [ ] **Step 3: Write the implementation**

Add to `src/tradex/cli.py`, after the existing `config` group's commands:

```python
def _session_broker_default() -> str:
    from brokers.cli._preferences import PreferencesStore

    return PreferencesStore().get("broker.default")


@tradex.group()
@click.option("--broker", default=_session_broker_default, help="Broker id (paper/dhan/upstox).")
@click.option("--json", "as_json", is_flag=True, help="Emit raw JSON instead of Rich tables.")
@click.option("--yaml", "as_yaml", is_flag=True, help="Emit YAML instead of Rich tables.")
@click.option("--quiet", "-q", "quiet", is_flag=True, help="Suppress output (exit code only).")
@click.pass_context
def position(ctx: click.Context, broker: str, as_json: bool, as_yaml: bool, quiet: bool) -> None:
    """Position queries (read-only, no OMS required)."""
    ctx.ensure_object(dict)
    ctx.obj["broker"] = broker
    ctx.obj["json"] = as_json
    ctx.obj["yaml"] = as_yaml
    ctx.obj["quiet"] = quiet


@position.command("list")
@click.pass_context
def position_list(ctx: click.Context) -> None:
    """List open positions."""
    from brokers.cli._errors import _render_error
    from brokers.cli._render import json_mode, present
    from domain.connect_errors import ConnectError
    from tradex.session import open_session

    try:
        session = open_session(ctx.obj["broker"], mode="market")
    except ConnectError as exc:
        _render_error(exc)
        raise SystemExit(1) from exc
    try:
        present(ctx, session.account.positions(), title="Positions")
    finally:
        session.close()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/tradex/test_cli_position.py -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
git add src/tradex/cli.py tests/unit/tradex/test_cli_position.py
git commit -m "feat(cli): add tradex position list"
```

---

### Task 2: `tradex portfolio`

**Files:**
- Modify: `src/tradex/cli.py`
- Test: `tests/unit/tradex/test_cli_portfolio.py`

**Interfaces:**
- Consumes: `session.account.refresh()` then the `@property` accessors `.portfolio -> Portfolio`, `.holdings -> list`, `.funds -> Any | None` (`AccountView`, `domain/portfolio/account_view.py` — these are properties, not methods; `AccountView.refresh()` must be called first or they silently return empty defaults from `__init__`. Found the hard way implementing Task 1's `position list` — see that task's commit message).
- Produces: `tradex portfolio [show|holdings|funds] [--broker BROKER]` (group flags precede the subcommand: `tradex portfolio --broker paper show`), defaulting `show` when no subcommand is given is NOT supported by plain Click groups without a default-command shim — instead ship three explicit subcommands (`show` is the primary one named to match the spec's `tradex portfolio` bare usage as closely as Click allows: alias `show` as the group's only always-relevant command; `holdings`/`funds` are siblings).
- Consumes (Task 1, already implemented): `tradex.cli._open_market_session(ctx)` and `tradex.cli._session_broker_default()` already exist in `src/tradex/cli.py` — reuse them, do not redefine.

- [ ] **Step 1: Write the failing test**

```python
"""Tests for `tradex portfolio`."""

from __future__ import annotations

import pytest
from click.testing import CliRunner

from tradex.cli import tradex


@pytest.mark.unit
def test_portfolio_show_paper_runs_clean() -> None:
    result = CliRunner().invoke(tradex, ["portfolio", "--broker", "paper", "show"])
    assert result.exit_code == 0, result.output


@pytest.mark.unit
def test_portfolio_holdings_paper_runs_clean() -> None:
    result = CliRunner().invoke(tradex, ["portfolio", "--broker", "paper", "holdings"])
    assert result.exit_code == 0, result.output


@pytest.mark.unit
def test_portfolio_funds_paper_runs_clean() -> None:
    result = CliRunner().invoke(tradex, ["portfolio", "--broker", "paper", "funds"])
    assert result.exit_code == 0, result.output
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/tradex/test_cli_portfolio.py -v`
Expected: FAIL — `Error: No such command 'portfolio'`.

- [ ] **Step 3: Write the implementation**

Add to `src/tradex/cli.py` (reusing the existing `_session_broker_default` and `_open_market_session` helpers from Task 1 — do not redefine them):

```python
@tradex.group()
@click.option("--broker", default=_session_broker_default, help="Broker id (paper/dhan/upstox).")
@click.option("--json", "as_json", is_flag=True, help="Emit raw JSON instead of Rich tables.")
@click.option("--yaml", "as_yaml", is_flag=True, help="Emit YAML instead of Rich tables.")
@click.option("--quiet", "-q", "quiet", is_flag=True, help="Suppress output (exit code only).")
@click.pass_context
def portfolio(ctx: click.Context, broker: str, as_json: bool, as_yaml: bool, quiet: bool) -> None:
    """Portfolio queries (read-only, no OMS required)."""
    ctx.ensure_object(dict)
    ctx.obj["broker"] = broker
    ctx.obj["json"] = as_json
    ctx.obj["yaml"] = as_yaml
    ctx.obj["quiet"] = quiet


@portfolio.command("show")
@click.pass_context
def portfolio_show(ctx: click.Context) -> None:
    """Show portfolio summary."""
    from brokers.cli._render import present

    session = _open_market_session(ctx)
    try:
        present(ctx, session.account.refresh().portfolio, title="Portfolio")
    finally:
        session.close()


@portfolio.command("holdings")
@click.pass_context
def portfolio_holdings(ctx: click.Context) -> None:
    """Show holdings."""
    from brokers.cli._render import present

    session = _open_market_session(ctx)
    try:
        present(ctx, session.account.refresh().holdings, title="Holdings")
    finally:
        session.close()


@portfolio.command("funds")
@click.pass_context
def portfolio_funds(ctx: click.Context) -> None:
    """Show available funds."""
    from brokers.cli._render import present

    session = _open_market_session(ctx)
    try:
        present(ctx, session.account.refresh().funds, title="Funds")
    finally:
        session.close()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/tradex/test_cli_portfolio.py tests/unit/tradex/test_cli_position.py -v`
Expected: PASS (5 tests)

- [ ] **Step 5: Commit**

```bash
git add src/tradex/cli.py tests/unit/tradex/test_cli_portfolio.py
git commit -m "feat(cli): add tradex portfolio show/holdings/funds; dedupe session-open helper"
```

---

### Task 3: `tradex order place` (paper safe-by-default, live requires confirmation + `mode=trade`)

**Files:**
- Modify: `src/tradex/cli.py`
- Test: `tests/unit/tradex/test_cli_order.py`

**Interfaces:**
- Consumes: `open_session(broker, mode="trade")` → `.universe.equity(symbol) -> Instrument`, `.buy(instrument, qty, price=None, order_type=OrderType.LIMIT, product_type=ProductType.INTRADAY) -> OrderResult`, `.sell(...)` (same signature), `OrderResult.success: bool`, `.order`, `.error: str` (`domain/ports/protocols.py`).
- Produces: `tradex order place SYMBOL QUANTITY [--side BUY|SELL] [--price PRICE] [--order-type TYPE] [--product-type TYPE] [--broker BROKER] [--yes/-y]`.

- [ ] **Step 1: Write the failing tests**

```python
"""Tests for `tradex order place`."""

from __future__ import annotations

import pytest
from click.testing import CliRunner

from tradex.cli import tradex


@pytest.mark.unit
def test_order_place_paper_never_prompts() -> None:
    """Paper is safe-by-default -- no confirmation, no --yes needed."""
    result = CliRunner().invoke(
        tradex,
        ["order", "--broker", "paper", "place", "RELIANCE", "1", "--price", "2500"],
    )
    assert result.exit_code == 0, result.output
    assert "Confirm" not in result.output


@pytest.mark.unit
def test_order_place_defaults_to_buy() -> None:
    result = CliRunner().invoke(
        tradex,
        ["order", "--broker", "paper", "place", "RELIANCE", "1", "--price", "2500"],
    )
    assert result.exit_code == 0, result.output
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/tradex/test_cli_order.py -v`
Expected: FAIL — `Error: No such command 'order'`.

- [ ] **Step 3: Write the implementation**

Add to `src/tradex/cli.py`:

```python
@tradex.group()
@click.option("--broker", default=_session_broker_default, help="Broker id (paper/dhan/upstox).")
@click.option("--json", "as_json", is_flag=True, help="Emit raw JSON instead of Rich tables.")
@click.option("--yaml", "as_yaml", is_flag=True, help="Emit YAML instead of Rich tables.")
@click.option("--quiet", "-q", "quiet", is_flag=True, help="Suppress output (exit code only).")
@click.pass_context
def order(ctx: click.Context, broker: str, as_json: bool, as_yaml: bool, quiet: bool) -> None:
    """Order placement -- routes through OMS + RiskGate (mode=trade)."""
    ctx.ensure_object(dict)
    ctx.obj["broker"] = broker
    ctx.obj["json"] = as_json
    ctx.obj["yaml"] = as_yaml
    ctx.obj["quiet"] = quiet


@order.command("place")
@click.argument("symbol")
@click.argument("quantity", type=int)
@click.option("--side", default="BUY", type=click.Choice(["BUY", "SELL"], case_sensitive=False))
@click.option("--price", default=None, type=float)
@click.option("--order-type", "order_type", default="LIMIT")
@click.option("--product-type", "product_type", default="INTRADAY")
@click.option("--yes", "-y", is_flag=True, help="Skip the live-broker confirmation prompt.")
@click.pass_context
def order_place(
    ctx: click.Context,
    symbol: str,
    quantity: int,
    side: str,
    price: float | None,
    order_type: str,
    product_type: str,
    yes: bool,
) -> None:
    """Place SYMBOL QUANTITY (paper-safe by default; live requires confirmation)."""
    from decimal import Decimal

    from brokers.cli._errors import _render_error
    from brokers.cli._render import present
    from domain.connect_errors import ConnectError
    from tradex.session import open_session

    broker_id = ctx.obj["broker"]
    is_live = broker_id not in {"paper", "datalake"}
    if is_live and not yes:
        if not click.confirm(
            f"Place {side} {quantity} {symbol} on LIVE broker {broker_id!r}?"
        ):
            click.echo("Aborted.")
            return

    try:
        session = open_session(broker_id, mode="trade")
    except ConnectError as exc:
        _render_error(exc)
        raise SystemExit(1) from exc
    try:
        instrument = session.universe.equity(symbol)
        px = Decimal(str(price)) if price is not None else None
        fn = session.sell if side.upper() == "SELL" else session.buy
        result = fn(instrument, quantity, price=px, order_type=order_type, product_type=product_type)
        if not result.success:
            raise click.ClickException(result.error or "order rejected")
        present(ctx, result.order, title="Order placed")
    finally:
        session.close()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/tradex/test_cli_order.py -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
git add src/tradex/cli.py tests/unit/tradex/test_cli_order.py
git commit -m "feat(cli): add tradex order place (mode=trade, live requires confirmation)"
```

---

### Task 4: Full verification + docs

- [ ] **Step 1:** `pytest tests/unit/tradex/ tests/unit/brokers/cli/ -q` — expect only the 4 pre-existing unrelated failures from Phase 1.
- [ ] **Step 2:** `ruff check src/tradex/cli.py` and `mypy src/tradex/cli.py` — fix anything genuinely new (compare against pre-task baseline counts, same method as Phase 1).
- [ ] **Step 3:** Update `context/progress-tracker.md` with a Phase 2 completion entry, naming what's still deferred (`order cancel/modify`, `account`, instruments, token, wizards).
- [ ] **Step 4:** Commit docs.
