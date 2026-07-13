"""Symbol & Instrument schemas."""

from __future__ import annotations

from pydantic import BaseModel, Field


class SymbolSearchRequest(BaseModel):
    """Symbol search query parameters."""

    q: str = Field(..., description="Search query", min_length=1, max_length=50)
    exchange: str | None = Field(None, description="Filter by exchange (NSE, BSE, MCX)")
    limit: int = Field(25, ge=1, le=100, description="Max results")


class SymbolInfo(BaseModel):
    """Complete symbol metadata."""

    symbol: str
    exchange: str
    name: str | None = None
    segment: str | None = None
    isin: str | None = None
    lot_size: int = 1
    tick_size: float = 0.05
    sector: str | None = None
    instrument_type: str = "EQUITY"
    first_date: str | None = None
    last_date: str | None = None
    total_rows: int = 0


class SymbolSearchResponse(BaseModel):
    """Symbol search results."""

    results: list[SymbolInfo]
    count: int


class UniverseResponse(BaseModel):
    """Universe symbol list."""

    name: str
    symbols: list[str]
    count: int
