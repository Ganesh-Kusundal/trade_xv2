"""Tests for the broker interactive shell."""

from __future__ import annotations

from click.testing import CliRunner

from brokers.cli.broker import broker


def _patch_rich(monkeypatch) -> None:
    monkeypatch.setattr("brokers.cli._shell_nav.json_mode", lambda ctx: False)


class _FakeSession:
    broker_id = "paper"

    def close(self) -> None:
        pass

    @property
    def status(self):
        return type("S", (), {"mode": "paper", "orders_enabled": False, "authenticated": True, "instruments_loaded": True})()

    @property
    def runtime(self):
        return type("R", (), {"checkpoints": []})()


def _patch_paper_session(monkeypatch) -> _FakeSession:
    """Shell holds one session; paper connect always succeeds."""
    sess = _FakeSession()
    monkeypatch.setattr("brokers.cli.broker.BrokerSession", lambda *_a, **_k: sess)
    monkeypatch.setattr(
        "brokers.cli.broker.status_from_session",
        lambda _s: {
            "broker_id": "paper",
            "connected": True,
            "mode": "paper",
            "orders_enabled": False,
            "authenticated": True,
            "instruments_loaded": True,
            "checkpoints": [],
        },
    )
    monkeypatch.setattr("brokers.cli.broker.extensions_from_session", lambda _s: [])
    return sess


def test_shell_exits_on_quit(monkeypatch) -> None:
    _patch_rich(monkeypatch)
    _patch_paper_session(monkeypatch)
    inputs = iter(["quit"])
    monkeypatch.setattr("builtins.input", lambda _: next(inputs))
    res = CliRunner().invoke(broker, ["--broker", "paper", "shell"])
    assert res.exit_code == 0, res.output
    assert "Trading OS Broker Shell" in res.output
    assert "Main menu" in res.output


def test_shell_exits_on_eof(monkeypatch) -> None:
    _patch_paper_session(monkeypatch)

    def _eof(_: str) -> str:
        raise EOFError

    monkeypatch.setattr("builtins.input", _eof)
    res = CliRunner().invoke(broker, ["--broker", "paper", "shell"])
    assert res.exit_code == 0, res.output


def test_shell_enter_market_then_exit(monkeypatch) -> None:
    _patch_rich(monkeypatch)
    _patch_paper_session(monkeypatch)
    inputs = iter(["2", "exit", "quit"])
    monkeypatch.setattr("builtins.input", lambda _: next(inputs))
    res = CliRunner().invoke(broker, ["--broker", "paper", "shell"])
    assert res.exit_code == 0, res.output
    assert "Market" in res.output


def test_shell_run_discover_from_main(monkeypatch) -> None:
    _patch_rich(monkeypatch)
    _patch_paper_session(monkeypatch)
    inputs = iter(["discover", "quit"])
    monkeypatch.setattr("builtins.input", lambda _: next(inputs))
    res = CliRunner().invoke(broker, ["--broker", "paper", "shell"])
    assert res.exit_code == 0, res.output
    assert "paper" in res.output


def test_shell_session_menu_discover(monkeypatch) -> None:
    _patch_rich(monkeypatch)
    _patch_paper_session(monkeypatch)
    inputs = iter(["1", "2", "quit"])
    monkeypatch.setattr("builtins.input", lambda _: next(inputs))
    res = CliRunner().invoke(broker, ["--broker", "paper", "shell"])
    assert res.exit_code == 0, res.output
    assert "paper" in res.output


def test_shell_exit_returns_main_not_quit(monkeypatch) -> None:
    _patch_rich(monkeypatch)
    _patch_paper_session(monkeypatch)
    inputs = iter(["2", "exit", "1", "quit"])
    monkeypatch.setattr("builtins.input", lambda _: next(inputs))
    res = CliRunner().invoke(broker, ["--broker", "paper", "shell"])
    assert res.exit_code == 0, res.output
    assert "Main menu" in res.output


def test_shell_help_command(monkeypatch) -> None:
    _patch_rich(monkeypatch)
    _patch_paper_session(monkeypatch)
    inputs = iter(["help", "quit"])
    monkeypatch.setattr("builtins.input", lambda _: next(inputs))
    res = CliRunner().invoke(broker, ["--broker", "paper", "shell"])
    assert res.exit_code == 0, res.output
    assert "Main menu help" in res.output


def test_live_broker_recovery_then_quit(monkeypatch) -> None:
    def _fail_session(_broker_id: str, **_kwargs):
        raise RuntimeError("gateway failed")

    monkeypatch.setattr("brokers.cli.broker.BrokerSession", _fail_session)
    _patch_rich(monkeypatch)
    inputs = iter(["q"])
    monkeypatch.setattr("builtins.input", lambda _: next(inputs))
    res = CliRunner().invoke(broker, ["--broker", "dhan", "shell"])
    assert res.exit_code == 0, res.output
    assert "Recovery" in res.output
    assert "not connected" in res.output


def test_live_broker_recovery_connect_success(monkeypatch) -> None:
    calls = {"n": 0}

    def _connect(_broker_id: str, **_kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("gateway failed")
        return _FakeSession()

    monkeypatch.setattr("brokers.cli.broker.BrokerSession", _connect)
    monkeypatch.setattr(
        "brokers.cli.broker.status_from_session",
        lambda _s: {
            "broker_id": "dhan",
            "connected": True,
            "mode": "live",
            "orders_enabled": True,
            "checkpoints": [],
        },
    )
    monkeypatch.setattr("brokers.cli.broker.extensions_from_session", lambda _s: [])
    _patch_rich(monkeypatch)
    inputs = iter(["1", "quit"])
    monkeypatch.setattr("builtins.input", lambda _: next(inputs))
    res = CliRunner().invoke(broker, ["--broker", "dhan", "shell"])
    assert res.exit_code == 0, res.output
    assert "Main menu" in res.output


def test_shell_quote_passes_broker_id_and_session(monkeypatch) -> None:
    sess = _FakeSession()
    sess.broker_id = "dhan"
    seen: list[tuple[str, object | None]] = []

    def _quote(broker_id: str, symbol: str, **kwargs) -> dict:
        seen.append((broker_id, kwargs.get("session")))
        return {"symbol": symbol, "ltp": "1"}

    monkeypatch.setattr("brokers.cli.broker.BrokerSession", lambda *_a, **_k: sess)
    monkeypatch.setattr(
        "brokers.cli.broker.status_from_session",
        lambda _s: {"broker_id": "dhan", "connected": True, "mode": "live", "orders_enabled": True, "checkpoints": []},
    )
    monkeypatch.setattr("brokers.cli.broker.extensions_from_session", lambda _s: [])
    monkeypatch.setattr("brokers.cli.broker.get_quote", _quote)
    _patch_rich(monkeypatch)
    inputs = iter(["quote TCS", "quit"])
    monkeypatch.setattr("builtins.input", lambda _: next(inputs))
    res = CliRunner().invoke(broker, ["--broker", "dhan", "shell"])
    assert res.exit_code == 0, res.output
    assert seen == [("dhan", sess)]


def test_shell_opens_one_session_for_startup_and_command(monkeypatch) -> None:
    open_calls = {"n": 0}
    sess = _FakeSession()

    def _counting_session(*_a, **_k):
        open_calls["n"] += 1
        return sess

    monkeypatch.setattr("brokers.cli.broker.BrokerSession", _counting_session)
    monkeypatch.setattr(
        "brokers.cli.broker.status_from_session",
        lambda _s: {"broker_id": "paper", "connected": True, "mode": "paper", "orders_enabled": False, "checkpoints": []},
    )
    monkeypatch.setattr("brokers.cli.broker.extensions_from_session", lambda _s: [])
    monkeypatch.setattr(
        "brokers.cli.broker.get_quote",
        lambda broker_id, symbol, **kwargs: {"symbol": symbol, "session": kwargs.get("session")},
    )
    _patch_rich(monkeypatch)
    inputs = iter(["quote TCS", "quit"])
    monkeypatch.setattr("builtins.input", lambda _: next(inputs))
    res = CliRunner().invoke(broker, ["--broker", "paper", "shell"])
    assert res.exit_code == 0, res.output
    assert open_calls["n"] == 1
