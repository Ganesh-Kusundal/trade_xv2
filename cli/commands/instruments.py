"""CLI command handler for the ``tradex instruments ...`` subcommand.

Implements the audit's §8 search & lookup diagnostics, backed by the
canonical :class:`brokers.dhan.instrument_service.InstrumentService`
(M3+ M5).  Subcommands:

* ``tradex instruments lookup <SYMBOL>``     — primary debug tool
* ``tradex instruments diagnostics``        — startup-validation report
* ``tradex instruments validate``           — validate the cached snapshot
* ``tradex instruments refresh``            — re-download the daily snapshot

The lookup command resolves any of:

* ``RELIANCE``
* ``NSE:RELIANCE`` / ``BSE:RELIANCE`` / ``NSE_EQ:RELIANCE``
* ``RELIANCE-EQ`` / ``RELIANCE-BE``
* ``NIFTY 50``
* ``RELIANCE FUT`` / ``NIFTY 30 JUN FUT`` / ``RELIANCE25JUNFUT``
* ``NIFTY 25000 CE`` / ``NIFTY 30 JUN 25000 CE`` / ``NIFTY30JUN25000CE``

and prints a Rich table with security ID, exchange, segment, instrument
type, expiry, strike, and option type.
"""

from __future__ import annotations

import logging
from pathlib import Path

from rich.console import Console
from rich.table import Table

from brokers.dhan.instrument_service import (
    InstrumentNotFoundError,
    InstrumentService,
    SnapshotInfo,
)
from brokers.dhan.mapper.instruments import (
    CatalogDiagnostics,
    DhanInstrumentDefinition,
    ResolutionResult,
    validate_snapshot,
)

logger = logging.getLogger(__name__)

# Where the daily snapshot lives by default.  Operators can override with
# the ``DHAN_INSTRUMENT_CACHE_DIR`` env var.
DEFAULT_CACHE_DIR = Path("runtime-dev/instruments")


def _resolve_cache_dir(explicit: Path | None = None) -> Path:
    if explicit is not None:
        return explicit
    import os

    env = os.environ.get("DHAN_INSTRUMENT_CACHE_DIR")
    return Path(env) if env else DEFAULT_CACHE_DIR


def _get_service(cache_dir: Path, strict_resolution: bool = True) -> InstrumentService:
    """Build an :class:`InstrumentService` and load the daily snapshot.

    M5: this is the new canonical path.  It uses the service's own
    ``refresh_snapshot`` so the snapshot, the checksum, and the
    in-memory indexes are all in one place.  ``strict_resolution=True``
    (default) means an unknown symbol raises
    :class:`InstrumentNotFoundError` — see M2 for the fail-loud rationale.
    """
    service = InstrumentService(
        cache_dir=cache_dir,
        strict_resolution=strict_resolution,
    )
    service.refresh_snapshot(force=False)
    return service


def _format_definition(defn: DhanInstrumentDefinition) -> Table:
    """Build a single-row Rich table showing the resolved instrument."""
    t = Table(
        title=f"Resolved Instrument: {defn.symbol}",
        header_style="bold cyan",
    )
    t.add_column("Field", style="bold white")
    t.add_column("Value", style="white")
    t.add_row("Symbol", defn.symbol)
    t.add_row("Canonical Symbol", defn.canonical_symbol)
    t.add_row("Security ID", defn.security_id)
    t.add_row("Exchange", defn.exchange)
    t.add_row("Segment (canonical)", defn.exchange_segment.name)
    t.add_row("Segment (wire)", defn.exchange_segment.value)
    t.add_row("Instrument Type", defn.instrument_type)
    t.add_row("Underlying", defn.underlying or "—")
    t.add_row("Expiry", defn.expiry or "—")
    t.add_row("Strike (₹)", str(defn.strike) if defn.strike is not None else "—")
    t.add_row(
        "Strike (paisa)",
        str(defn.strike_price_paisa) if defn.strike_price_paisa is not None else "—",
    )
    t.add_row("Option Type", defn.option_type or "—")
    t.add_row("Lot Size", str(defn.lot_size))
    t.add_row("Tick Size", str(defn.tick_size))
    if defn.isin:
        t.add_row("ISIN", defn.isin)
    return t


def _format_ambiguous(result: ResolutionResult) -> Table:
    t = Table(title="Ambiguous Resolution", header_style="bold yellow")
    t.add_column("Symbol", style="bold white")
    t.add_column("Exchange")
    t.add_column("Segment (wire)")
    t.add_column("Security ID")
    for d in result.candidates:
        t.add_row(d.symbol, d.exchange, d.exchange_segment.value, d.security_id)
    t.add_row(
        "[yellow]Specify exchange (e.g. NSE:RELIANCE, BSE:RELIANCE)[/yellow]",
        "",
        "",
        "",
    )
    return t


def _format_unknown(result: ResolutionResult) -> Table:
    t = Table(title="Unknown Symbol", header_style="bold red")
    t.add_column("Field", style="bold white")
    t.add_column("Value")
    t.add_row("Reason", result.reason or "(no detail)")
    t.add_row(
        "Tip",
        "Try `NSE:RELIANCE` or `RELIANCE-EQ`. "
        "For F&O: `NIFTY 30 JUN 25000 CE` or `RELIANCE25JUNFUT`.",
    )
    return t


def _format_diagnostics(diag: CatalogDiagnostics) -> Table:
    t = Table(title="Catalog Diagnostics", header_style="bold magenta")
    t.add_column("Field", style="bold white")
    t.add_column("Value", justify="right")
    t.add_row("Record count", str(diag.record_count))
    t.add_row("by_security_id", str(diag.by_security_id_size))
    t.add_row("by_trading_symbol", str(diag.by_trading_symbol_size))
    t.add_row("by_custom_symbol", str(diag.by_custom_symbol_size))
    t.add_row("by_isin", str(diag.by_isin_size))
    t.add_row("by_exchange", str(diag.by_exchange_size))
    t.add_row("by_segment", str(diag.by_segment_size))
    t.add_row("Duplicate security IDs", str(len(diag.duplicate_security_ids)))
    t.add_row("Missing ISIN", str(diag.missing_isin_count))
    t.add_row("Missing exchange", str(diag.missing_exchange_count))
    t.add_row("Futures", str(diag.futures_count))
    t.add_row("Options", str(diag.options_count))
    t.add_row("Indices", str(diag.indices_count))
    t.add_row("Equities", str(diag.equities_count))
    t.add_row("Checksum (sha256)", diag.checksum or "—")
    return t


def _format_snapshot_info(info: SnapshotInfo) -> Table:
    """Render a :class:`SnapshotInfo` as a small Rich table."""
    t = Table(title="Instrument Snapshot", header_style="bold blue")
    t.add_column("Field", style="bold white")
    t.add_column("Value")
    t.add_row("Date", info.date)
    t.add_row("Source", str(info.source_path))
    t.add_row("Wire URL", info.wire_url)
    t.add_row("Record count", f"{info.record_count:,}")
    t.add_row("Checksum (sha256)", info.checksum or "—")
    return t


def run(args: list[str], console: Console) -> None:
    """Entry point for ``tradex instruments <subcommand>``."""
    if not args:
        console.print(
            "[yellow]Usage:[/yellow]\n"
            "  tradex instruments lookup <SYMBOL>\n"
            "  tradex instruments diagnostics\n"
            "  tradex instruments validate\n"
            "  tradex instruments refresh"
        )
        return

    sub = args[0].lower()
    rest = args[1:]

    if sub == "lookup":
        if not rest:
            console.print("[yellow]Usage: tradex instruments lookup <SYMBOL>[/yellow]")
            return
        symbol = " ".join(rest)
        _cmd_lookup(symbol, console)
    elif sub == "diagnostics":
        _cmd_diagnostics(console)
    elif sub == "validate":
        _cmd_validate(console)
    elif sub == "refresh":
        _cmd_refresh(console)
    else:
        console.print(f"[red]Unknown subcommand: {sub}[/red]")


def _cmd_lookup(symbol: str, console: Console) -> None:
    """M5 — lookup, backed by the canonical InstrumentService."""
    cache_dir = _resolve_cache_dir()
    try:
        service = _get_service(cache_dir)
    except Exception as exc:
        console.print(f"[red]Failed to load catalog: {exc}[/red]")
        return

    # The service is structured-result oriented.  Pull the same
    # ``ResolutionResult`` and translate to Rich tables.
    exchange = ""  # No exchange hint — let the chain probe.
    result = service.resolve_symbol(symbol, exchange)
    if result.is_single and result.definition is not None:
        console.print(_format_definition(result.definition))
        console.print(f"[dim]Reason: {result.reason}[/dim]")
    elif result.is_ambiguous:
        console.print(_format_ambiguous(result))
        console.print(f"[dim]Reason: {result.reason}[/dim]")
    else:
        console.print(_format_unknown(result))
        # Also offer the rich diagnostics block as a tail.
        try:
            diag_text = service.diagnostics(symbol, exchange)
            console.print(f"\n[dim]{diag_text}[/dim]")
        except InstrumentNotFoundError as exc:
            console.print(f"[dim]{exc}[/dim]")


def _cmd_diagnostics(console: Console) -> None:
    """M5 — full catalog diagnostics report."""
    cache_dir = _resolve_cache_dir()
    try:
        service = _get_service(cache_dir)
    except Exception as exc:
        console.print(f"[red]Failed to load catalog: {exc}[/red]")
        return
    # Catalog-level diagnostics come from the service's internal catalog
    # (the public service API exposes snapshot info; the catalog itself
    # is still accessible for diagnostics).
    diag = service._indexes.catalog.diagnostics()
    console.print(_format_snapshot_info(service.snapshot_info))
    console.print(_format_diagnostics(diag))


def _cmd_validate(console: Console) -> None:
    """M5 — validate the cached snapshot."""
    cache_dir = _resolve_cache_dir()
    if not cache_dir.exists():
        console.print(f"[red]Cache dir does not exist: {cache_dir}[/red]")
        return
    # Find the latest snapshot in the cache dir
    snapshots = sorted(cache_dir.glob("api-scrip-master-*.csv"), reverse=True)
    if not snapshots:
        console.print(f"[red]No snapshot found in {cache_dir}[/red]")
        return
    path = snapshots[0]
    try:
        diag = validate_snapshot(path, require_unique_security_ids=False)
    except Exception as exc:
        console.print(f"[red]Validation failed: {exc}[/red]")
        return
    console.print(f"[green]Snapshot OK:[/green] {path}")
    console.print(_format_diagnostics(diag))


def _cmd_refresh(console: Console) -> None:
    """M5 — re-download the daily snapshot."""
    cache_dir = _resolve_cache_dir()
    cache_dir.mkdir(parents=True, exist_ok=True)
    try:
        service = InstrumentService(cache_dir=cache_dir)
        info = service.refresh_snapshot(force=True)
    except Exception as exc:
        console.print(f"[red]Refresh failed: {exc}[/red]")
        return
    console.print(f"[green]Refreshed:[/green] {info.record_count:,} records")
    console.print(_format_snapshot_info(info))
