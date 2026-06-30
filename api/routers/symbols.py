"""Symbol search and metadata endpoints."""

from __future__ import annotations

import logging
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, status

from api.auth import require_auth
from api.deps import get_data_catalog
from api.schemas import (
    SymbolInfo,
    SymbolSearchResponse,
    UniverseResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(dependencies=[Depends(require_auth)])


@router.get("/search", response_model=SymbolSearchResponse)
async def search_symbols(
    q: str = Query(..., min_length=1, max_length=50, description="Search query"),
    exchange: str | None = Query(None, description="Filter by exchange"),
    limit: int = Query(25, ge=1, le=100, description="Max results"),
):
    """Search symbols by name or symbol code.

    Searches across symbol code, company name, and ISIN.
    Returns matching symbols with metadata.
    """
    catalog = get_data_catalog()

    try:
        # Query DataCatalog for matching symbols
        query = """
            SELECT symbol, exchange, sector, isin, lot_size, tick_size,
                   instrument_type, first_date, last_date, total_rows
            FROM symbols
            WHERE UPPER(symbol) LIKE UPPER(?)
               OR UPPER(sector) LIKE UPPER(?)
               OR UPPER(isin) LIKE UPPER(?)
        """

        search_pattern = f"%{q.upper()}%"
        params = [search_pattern, search_pattern, search_pattern]

        if exchange:
            query += " AND UPPER(exchange) = UPPER(?)"
            params.append(exchange.upper())

        query += " ORDER BY symbol LIMIT ?"
        params.append(limit)

        results = catalog.conn.execute(query, params).fetchall()

        symbols = [
            SymbolInfo(
                symbol=row[0],
                exchange=row[1],
                sector=row[2] or "",
                isin=row[3] or "",
                lot_size=row[4] or 1,
                tick_size=row[5] or 0.05,
                instrument_type=row[6] or "EQUITY",
                first_date=str(row[7]) if row[7] else None,
                last_date=str(row[8]) if row[8] else None,
                total_rows=row[9] or 0,
            )
            for row in results
        ]

        return SymbolSearchResponse(results=symbols, count=len(symbols))

    except Exception as exc:
        logger.error("Symbol search failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Symbol search failed: {exc!s}",
        ) from exc


@router.get("/{symbol}", response_model=SymbolInfo)
async def get_symbol(symbol: str):
    """Get full metadata for a symbol.

    Returns complete instrument information including
    lot size, tick size, sector, and data availability.
    """
    catalog = get_data_catalog()

    try:
        query = """
            SELECT symbol, exchange, sector, isin, lot_size, tick_size,
                   instrument_type, first_date, last_date, total_rows
            FROM symbols
            WHERE UPPER(symbol) = UPPER(?)
        """

        result = catalog.conn.execute(query, [symbol.upper()]).fetchone()

        if result is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Symbol '{symbol}' not found",
            )

        return SymbolInfo(
            symbol=result[0],
            exchange=result[1],
            sector=result[2] or "",
            isin=result[3] or "",
            lot_size=result[4] or 1,
            tick_size=result[5] or 0.05,
            instrument_type=result[6] or "EQUITY",
            first_date=str(result[7]) if result[7] else None,
            last_date=str(result[8]) if result[8] else None,
            total_rows=result[9] or 0,
        )

    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Symbol lookup failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Symbol lookup failed: {exc!s}",
        ) from exc


@router.get("/universe/{name}", response_model=UniverseResponse)
async def get_universe(name: str):
    """Get symbols in a universe (NIFTY50, NIFTY100, NIFTY200, NIFTY500, BANKNIFTY, FINNIFTY).

    Reads from static universe files in data/universes/.
    """
    valid_universes = ["nifty50", "nifty100", "nifty200", "nifty500", "banknifty", "finnifty"]

    if name.lower() not in valid_universes:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid universe '{name}'. Valid: {', '.join(valid_universes)}",
        )

    try:
        # Try to load from universe file
        universe_file = Path("data/universes") / f"{name.lower()}.txt"

        if not universe_file.exists():
            # Fallback to CSV files in root
            csv_file = Path(f"ind_{name.lower()}.csv")
            if csv_file.exists():
                symbols = []
                with open(csv_file) as f:
                    for line in f:
                        line = line.strip()
                        if line and not line.startswith("#"):
                            symbols.append(line.split(",")[0])
            else:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Universe file for '{name}' not found",
                )
        else:
            symbols = universe_file.read_text().splitlines()
            symbols = [s.strip() for s in symbols if s.strip() and not s.startswith("#")]

        return UniverseResponse(
            name=name.upper(),
            symbols=symbols,
            count=len(symbols),
        )

    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Universe lookup failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Universe lookup failed: {exc!s}",
        ) from exc
