"""End-to-end smoke test for the ``tradex instruments lookup`` CLI command.

Loads a real (or realistic) Dhan snapshot, then runs the resolver
through the CLI surface.  No network access required.
"""

from __future__ import annotations

import io
from datetime import date

import pytest
from rich.console import Console

from cli.commands import instruments as cmd_instruments


@pytest.fixture()
def temp_cache_dir(tmp_path, monkeypatch):
    """Build a tiny but representative Dhan snapshot in a temp dir."""
    cache = tmp_path / "instruments"
    cache.mkdir()
    csv_path = cache / f"api-scrip-master-{date.today()}.csv"
    csv_path.write_text(
        "SEM_EXM_EXCH_ID,SEM_SEGMENT,SEM_SMST_SECURITY_ID,SEM_INSTRUMENT_NAME,"
        "SEM_EXPIRY_CODE,SEM_TRADING_SYMBOL,SEM_LOT_UNITS,SEM_CUSTOM_SYMBOL,"
        "SEM_EXPIRY_DATE,SEM_STRIKE_PRICE,SEM_OPTION_TYPE,SEM_TICK_SIZE,"
        "SEM_EXPIRY_FLAG,SEM_EXCH_INSTRUMENT_TYPE,SEM_SERIES,SM_SYMBOL_NAME\n"
        "NSE,E,2885,EQUITY,0,RELIANCE,1.0,Reliance Industries,,,"
        "XX,10.0,NA,ES,EQ,\n"
        "BSE,E,500325,EQUITY,0,RELIANCE,1.0,Reliance Industries,,,"
        "XX,5.0,NA,ES,A,\n"
        "NSE,I,13,INDEX,0,NIFTY,1.0,Nifty 50,,,XX,0.05,,INDEX,X,\n"
        "NSE,I,25,INDEX,0,BANKNIFTY,1.0,Nifty Bank,,,XX,0.05,,INDEX,X,\n"
        "NSE,D,61284,FUTSTK,0,RELIANCE-Jul2026-FUT,500.0,RELIANCE JUL FUT,"
        "2026-07-28 14:30:00,-0.01000,XX,10.0,M,FUT,,\n"
        "NSE,D,1103387,OPTSTK,0,RELIANCE-Jun2026-1400-CE,500.0,"
        "RELIANCE 25 JUN 1400 CALL,2026-06-25 15:30:00,1400.00000,CE,5.0,M,OPTSTK,,\n"
    )
    # Force the CLI to look at our temp cache dir
    monkeypatch.setenv("DHAN_INSTRUMENT_CACHE_DIR", str(cache))
    return cache


def test_cli_lookup_equity_nse(temp_cache_dir):
    console = Console(file=io.StringIO(), force_terminal=False, width=200)
    cmd_instruments.run(["lookup", "NSE:RELIANCE"], console)
    output = console.file.getvalue()
    assert "Resolved Instrument: RELIANCE" in output
    assert "Security ID" in output
    assert "2885" in output
    assert "NSE_EQ" in output


def test_cli_lookup_equity_bse(temp_cache_dir):
    console = Console(file=io.StringIO(), force_terminal=False, width=200)
    cmd_instruments.run(["lookup", "BSE:RELIANCE"], console)
    output = console.file.getvalue()
    assert "500325" in output


def test_cli_lookup_ambiguous(temp_cache_dir):
    console = Console(file=io.StringIO(), force_terminal=False, width=200)
    cmd_instruments.run(["lookup", "RELIANCE"], console)
    output = console.file.getvalue()
    assert "Ambiguous Resolution" in output
    assert "Specify exchange" in output
    assert "2885" in output
    assert "500325" in output


def test_cli_lookup_option_compact(temp_cache_dir):
    console = Console(file=io.StringIO(), force_terminal=False, width=200)
    cmd_instruments.run(["lookup", "RELIANCE25JUN1400CE"], console)
    output = console.file.getvalue()
    assert "1103387" in output
    assert "Option Type" in output
    assert "Strike (paisa)" in output


def test_cli_lookup_index(temp_cache_dir):
    console = Console(file=io.StringIO(), force_terminal=False, width=200)
    cmd_instruments.run(["lookup", "NIFTY"], console)
    output = console.file.getvalue()
    assert "13" in output
    assert "INDEX" in output


def test_cli_lookup_unknown(temp_cache_dir):
    console = Console(file=io.StringIO(), force_terminal=False, width=200)
    cmd_instruments.run(["lookup", "TOTALLY_FAKE_XYZ"], console)
    output = console.file.getvalue()
    assert "Unknown Symbol" in output


def test_cli_diagnostics(temp_cache_dir):
    console = Console(file=io.StringIO(), force_terminal=False, width=200)
    cmd_instruments.run(["diagnostics"], console)
    output = console.file.getvalue()
    assert "Catalog Diagnostics" in output
    assert "Record count" in output
    assert "Checksum" in output


def test_cli_validate(temp_cache_dir):
    console = Console(file=io.StringIO(), force_terminal=False, width=200)
    cmd_instruments.run(["validate"], console)
    output = console.file.getvalue()
    assert "Snapshot OK" in output
