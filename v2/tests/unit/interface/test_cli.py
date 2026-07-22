"""CLI — tradex version via main(argv)."""

from __future__ import annotations

from tradex.cli import main


def test_version(capsys) -> None:
    code = main(["version"])
    assert code == 0
    out = capsys.readouterr().out
    assert "0.1.0" in out or "tradex" in out.lower()
