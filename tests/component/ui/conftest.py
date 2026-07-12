"""Shared fixtures and gate helpers for CLI endpoint tests.

Provides:

* ``project_root``         — path to repo root
* ``tradex_python``        — interpreter used to launch ``cli.main``
* ``run_cli``              — subprocess wrapper for end-to-end routing tests
* ``live_dhan_available``  — skip-if-creds-missing gate
* ``sandbox_enabled``      — DHAN_INTEGRATION=1 opt-in
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[3]


def _resolve_tradex_python() -> str:
    """Pick the Python interpreter matching the active venv.

    Preference order:
    1. ``TRADEX_PYTHON`` env var (CI override)
    2. ``./tradex`` launcher — reuses whatever it currently points at
    3. ``sys.executable`` — falls back to whatever pytest itself is using
    """
    override = os.environ.get("TRADEX_PYTHON")
    if override:
        return override

    launcher = PROJECT_ROOT / "tradex"
    # Prefer a real launcher script; skip if ``tradex`` is the package directory.
    if launcher.is_file():
        # Read the exec line to discover which python the launcher uses.
        text = launcher.read_text()
        if "python" in text:
            for tok in text.split():
                if "python" in tok and "bin" in tok and Path(tok).exists():
                    return tok

    return sys.executable


TRADEX_PYTHON = _resolve_tradex_python()


# ── Fixtures ──────────────────────────────────────────────────────────


@pytest.fixture(scope="session")
def project_root() -> Path:
    return PROJECT_ROOT


@pytest.fixture(scope="session")
def tradex_python() -> str:
    return TRADEX_PYTHON


@dataclass(frozen=True)
class CliResult:
    returncode: int
    stdout: str
    stderr: str
    timeout: bool = False


@pytest.fixture()
def run_cli(tradex_python: str, project_root: Path, tmp_path: Path):
    """Invoke ``python -m interface.ui.main <argv>`` as a subprocess.

    Captures stdout, stderr, and exit code. Uses ``tmp_path`` as the
    working directory so any side-effect files (cache, journal,
    events) land in a per-test scratch space and never touch the
    real ``runtime-dev/`` tree.
    """

    def _invoke(
        argv: list[str],
        *,
        timeout: int = 30,
        env_overrides: dict[str, str] | None = None,
        expect_exit_override: int | None = None,
    ) -> CliResult:
        env = os.environ.copy()
        env["PYTHONPATH"] = os.pathsep.join(
            [
                str(project_root / "src"),
                str(project_root),
                env.get("PYTHONPATH", ""),
            ]
        )
        # Force isolated, deterministic caching per test
        env["XDG_CACHE_HOME"] = str(tmp_path / "cache")
        env["HOME"] = str(tmp_path)  # isolate ~/.cache, .env, etc.
        if env_overrides:
            env.update(env_overrides)

        # Reuse the project's .env.local if present (live_readonly tests
        # need it); but copy it to tmp so we don't pollute the tree.
        env_file = project_root / ".env.local"
        env_copy = tmp_path / ".env.local"
        if env_file.exists():
            shutil.copy(env_file, env_copy)
        else:
            env_copy.write_text("")  # touch so create_gateway finds it

        # Seed empty state files so read-only commands that open
        # journal/options-sync DuckDB don't fail just because tmp_path
        # is empty. The CLI is allowed to use these as scratch — we
        # only care about the exit code and stdout shape.
        _seed_empty_state(tmp_path)

        try:
            proc = subprocess.run(
                [tradex_python, "-m", "interface.ui.main", *argv],
                cwd=str(tmp_path),
                env=env,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            return CliResult(
                returncode=proc.returncode,
                stdout=proc.stdout,
                stderr=proc.stderr,
                timeout=False,
            )
        except subprocess.TimeoutExpired as exc:
            return CliResult(
                returncode=-1,
                stdout=exc.stdout.decode() if isinstance(exc.stdout, bytes) else (exc.stdout or ""),
                stderr=(
                    exc.stderr.decode() if isinstance(exc.stderr, bytes) else (exc.stderr or "")
                )
                + f"\n[timeout after {timeout}s]",
                timeout=True,
            )

    return _invoke


# ── Skip gates ───────────────────────────────────────────────────────


def _env_local_has_credentials() -> bool:
    """Mirror the gate used in test_commands.py."""
    env = PROJECT_ROOT / ".env.local"
    if not env.exists():
        return False
    try:
        text = env.read_text()
    except OSError:
        return False
    for key in ("DHAN_CLIENT_ID", "DHAN_ACCESS_TOKEN", "DHAN_PIN"):
        for line in text.splitlines():
            if line.startswith(f"{key}=") and line.split("=", 1)[1].strip():
                return True
    return False


@pytest.fixture(scope="session")
def live_dhan_available() -> bool:
    return _env_local_has_credentials()


@pytest.fixture(scope="session")
def sandbox_enabled() -> bool:
    return os.environ.get("DHAN_INTEGRATION") == "1" and _env_local_has_credentials()


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    """Auto-skip live_readonly / sandbox tests when their gates fail.

    Avoids scattering skipif() across every test file. Tests opt in
    via the ``cli_endpoint_live`` or ``cli_endpoint_sandbox`` markers.
    """
    live_ok = _env_local_has_credentials()
    sandbox_ok = live_ok and os.environ.get("DHAN_INTEGRATION") == "1"

    for item in items:
        markers = {m.name for m in item.iter_markers()}
        if "cli_endpoint_live" in markers and not live_ok:
            item.add_marker(
                pytest.mark.skip(reason="live Dhan credentials not configured in .env.local")
            )
        if "cli_endpoint_sandbox" in markers and not sandbox_ok:
            item.add_marker(pytest.mark.skip(reason="DHAN_INTEGRATION=1 not set or creds missing"))


def _seed_empty_state(tmp_path: Path) -> None:
    """Pre-create empty state files that offline commands expect to open.

    `journal list` opens ``market_data/journal.sqlite`` in read-only
    mode; without a file that mode fails.  Seeding an empty schema
    file lets the read succeed and the command print "No trades
    found."  Similar for the DuckDB catalog — `views list` and
    `options-sync` need a writable catalog file.
    """
    # Journal SQLite (empty, schema applied)
    journal_dir = tmp_path / "market_data"
    journal_dir.mkdir(parents=True, exist_ok=True)
    journal_db = journal_dir / "journal.sqlite"
    if not journal_db.exists():
        import sqlite3

        conn = sqlite3.connect(str(journal_db))
        conn.executescript(
            "CREATE TABLE IF NOT EXISTS trade_journal ("
            "trade_id TEXT PRIMARY KEY, symbol TEXT, strategy TEXT,"
            "entry_time TEXT, exit_time TEXT, entry_price REAL,"
            "exit_price REAL, quantity INTEGER, side TEXT, pnl REAL,"
            "pnl_pct REAL, status TEXT DEFAULT 'OPEN', notes TEXT,"
            "metadata TEXT);"
        )
        conn.commit()
        conn.close()

    # DuckDB catalog — must be a valid empty database (not a zero-byte file).
    catalog = journal_dir / "catalog.duckdb"
    if not catalog.exists():
        import duckdb

        conn = duckdb.connect(str(catalog))
        conn.execute("SELECT 1")
        conn.close()
