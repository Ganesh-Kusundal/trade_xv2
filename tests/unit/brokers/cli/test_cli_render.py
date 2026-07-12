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
    _render_records(
        [{"a": 1, "b": "x"}, {"a": 2, "b": "y"}], "Rows", c
    )
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


def test_present_json_mode_when_piped(monkeypatch, capsys) -> None:
    monkeypatch.setattr("sys.stdout.isatty", lambda: False)
    present(None, {"symbol": "RELIANCE", "ltp": 2500.5})
    out = capsys.readouterr().out
    assert json.loads(out) == {"symbol": "RELIANCE", "ltp": 2500.5}


def test_present_json_mode_forced_by_flag(monkeypatch, capsys) -> None:
    monkeypatch.setattr("sys.stdout.isatty", lambda: True)

    class _Ctx:
        def __init__(self) -> None:
            self.obj = {"json": True}

    present(_Ctx(), {"symbol": "RELIANCE"})
    out = capsys.readouterr().out
    assert json.loads(out) == {"symbol": "RELIANCE"}


def test_cli_json_flag_emits_json(monkeypatch) -> None:
    monkeypatch.setattr(
        "brokers.cli.broker.get_quote",
        lambda b, symbol: {"symbol": symbol, "ltp": 123.0},
    )
    res = CliRunner().invoke(broker, ["--json", "--broker", "paper", "quote", "FOO"])
    assert res.exit_code == 0, res.output
    assert json.loads(res.output) == {"symbol": "FOO", "ltp": 123.0}


def test_cli_discover_runs() -> None:
    res = CliRunner().invoke(broker, ["--broker", "paper", "discover"])
    assert res.exit_code == 0
    assert "paper" in res.output
