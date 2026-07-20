"""Unit tests for the broker CLI Rich rendering and JSON fallback."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from decimal import Decimal
from io import StringIO

from click.testing import CliRunner
from rich.console import Console

from brokers.cli._render import _render_kv, _render_records, present
from brokers.cli.broker import broker
from brokers.services import safe_serialize
from domain.candles.historical import InstrumentRef
from domain.entities.market import QuoteSnapshot
from domain.provenance import DataProvenance, ProvenanceConfidence, SourceIdentity


def _sample_quote() -> QuoteSnapshot:
    return QuoteSnapshot(
        instrument=InstrumentRef(symbol="TCS", exchange="NSE"),
        ltp=Decimal("1037.38"),
        event_time=datetime(2026, 7, 11, 18, 26, 45, tzinfo=timezone.utc),
        provenance=DataProvenance(
            source=SourceIdentity(broker_id="dhan"),
            fetched_at=datetime(2026, 7, 11, 18, 26, 45, tzinfo=timezone.utc),
            request_id="dhan",
            confidence=ProvenanceConfidence.AUTHORITATIVE,
        ),
        open=Decimal("1055.47"),
        high=Decimal("1057.61"),
        low=Decimal("1035.16"),
        close=Decimal("1058.95"),
        volume=428853,
        bid=Decimal("1036.88"),
        ask=Decimal("1037.88"),
    )


def test_render_kv_rich() -> None:
    buf = StringIO()
    c = Console(file=buf, width=120)
    _render_kv({"symbol": "RELIANCE", "ltp": 2500.5}, "Quote", c)
    out = buf.getvalue()
    assert "symbol" in out and "RELIANCE" in out and "ltp" in out


def test_render_records_rich() -> None:
    buf = StringIO()
    c = Console(file=buf, width=120)
    _render_records([{"a": 1, "b": "x"}, {"a": 2, "b": "y"}], "Rows", c)
    out = buf.getvalue()
    assert "a" in out and "x" in out and "y" in out


def test_safe_serialize_quote_snapshot() -> None:
    data = safe_serialize(_sample_quote())
    assert isinstance(data, dict)
    assert data["ltp"] == "1037.38"


def test_present_quote_snapshot_table(monkeypatch) -> None:
    monkeypatch.setattr("sys.stdout.isatty", lambda: True)
    buf = StringIO()
    c = Console(file=buf, width=120)
    present(None, _sample_quote(), title="Quote — TCS", out=c)
    out = buf.getvalue()
    assert "ltp" in out and "1037.38" in out
    assert "source" in out and "dhan" in out
    assert "QuoteSnapshot(" not in out


def _sample_option_chain():
    from decimal import Decimal

    from domain.entities.options import OptionChain, OptionLeg, OptionStrike
    from domain.options.option_chain import OptionChain as OptionChainAggregate

    vo = OptionChain(
        underlying="NIFTY",
        exchange="NFO",
        expiry="2026-07-14",
        spot=Decimal("24200"),
        strikes=(
            OptionStrike(
                strike=Decimal("24100"),
                call=OptionLeg(ltp=Decimal("150"), oi=1000),
                put=OptionLeg(ltp=Decimal("80"), oi=900),
            ),
            OptionStrike(
                strike=Decimal("24200"),
                call=OptionLeg(ltp=Decimal("120"), oi=2000),
                put=OptionLeg(ltp=Decimal("110"), oi=1800),
            ),
            OptionStrike(
                strike=Decimal("24300"),
                call=OptionLeg(ltp=Decimal("90"), oi=800),
                put=OptionLeg(ltp=Decimal("140"), oi=1100),
            ),
        ),
    )
    return OptionChainAggregate(vo)


def test_present_option_chain_table(monkeypatch) -> None:
    monkeypatch.setattr("sys.stdout.isatty", lambda: True)
    buf = StringIO()
    c = Console(file=buf, width=140)
    present(None, _sample_option_chain(), title="Option chain — NIFTY", out=c)
    out = buf.getvalue()
    assert "CE LTP" in out and "PE LTP" in out and "Strike" in out
    assert "24200" in out and "120" in out and "110" in out
    assert ".000000" not in out
    assert "OptionStrike(" not in out
    assert "sample_strikes" not in out


def test_present_json_mode_when_piped(monkeypatch, caplog) -> None:
    monkeypatch.setattr("brokers.cli._render.sys.stdout.isatty", lambda: False)
    with caplog.at_level("INFO", logger="brokers.cli._render"):
        present(None, {"symbol": "RELIANCE", "ltp": 2500.5})
    assert json.loads(caplog.records[0].message) == {"symbol": "RELIANCE", "ltp": 2500.5}


def test_present_json_mode_forced_by_flag(monkeypatch, caplog) -> None:
    monkeypatch.setattr("brokers.cli._render.sys.stdout.isatty", lambda: True)

    class _Ctx:
        def __init__(self) -> None:
            self.obj = {"json": True}

    with caplog.at_level("INFO", logger="brokers.cli._render"):
        present(_Ctx(), {"symbol": "RELIANCE"})
    assert json.loads(caplog.records[0].message) == {"symbol": "RELIANCE"}


def test_cli_json_flag_emits_json(monkeypatch, caplog) -> None:
    monkeypatch.setattr(
        "brokers.cli.broker.get_quote",
        lambda b, symbol: {"symbol": symbol, "ltp": 123.0},
    )
    with caplog.at_level("INFO", logger="brokers.cli._render"):
        res = CliRunner().invoke(broker, ["--json", "--broker", "paper", "quote", "FOO"])
    assert res.exit_code == 0, res.output
    assert json.loads(caplog.records[-1].message) == {"symbol": "FOO", "ltp": 123.0}


def test_cli_discover_runs(caplog) -> None:
    with caplog.at_level("INFO", logger="brokers.cli._render"):
        res = CliRunner().invoke(broker, ["--json", "--broker", "paper", "discover"])
    assert res.exit_code == 0
    assert "paper" in caplog.text


def test_present_yaml_mode_emits_valid_yaml(caplog) -> None:
    # caplog attaches its own handler directly to the logger, so this is
    # reliable regardless of whether a stdout-bound handler is configured
    # for the process (present()'s json branch already relies on the same
    # logger.info() channel, and `capsys`/CliRunner-based assertions on
    # that channel are pre-existing-flaky in this environment — see
    # test_present_json_mode_when_piped/forced_by_flag above, which fail
    # even on origin HEAD; unrelated to this task).
    import yaml as _yaml

    class _Ctx:
        obj = {"yaml": True}

    with caplog.at_level("INFO", logger="brokers.cli._render"):
        present(_Ctx(), {"symbol": "FOO", "ltp": 123.0})
    assert len(caplog.records) == 1
    assert _yaml.safe_load(caplog.records[0].message) == {"symbol": "FOO", "ltp": 123.0}


def test_cli_quiet_flag_suppresses_output() -> None:
    res = CliRunner().invoke(broker, ["--quiet", "--broker", "paper", "discover"])
    assert res.exit_code == 0, res.output
    assert res.output.strip() == ""


def test_cli_quiet_short_flag() -> None:
    res = CliRunner().invoke(broker, ["-q", "--broker", "paper", "discover"])
    assert res.exit_code == 0, res.output
    assert res.output.strip() == ""


def test_present_quiet_mode_suppresses_rich_output_that_would_otherwise_print(monkeypatch) -> None:
    monkeypatch.setattr("sys.stdout.isatty", lambda: True)  # force human/Rich mode

    class _LoudCtx:
        obj = {"quiet": False}

    class _QuietCtx:
        obj = {"quiet": True}

    loud_buf = StringIO()
    present(_LoudCtx(), {"a": 1}, out=Console(file=loud_buf, width=120))
    assert loud_buf.getvalue() != ""  # baseline: this data does render when not quiet

    quiet_buf = StringIO()
    present(_QuietCtx(), {"a": 1}, out=Console(file=quiet_buf, width=120))
    assert quiet_buf.getvalue() == ""
