"""Upstox instrument cache adapter."""

from __future__ import annotations

import sqlite3
from typing import TYPE_CHECKING

from brokers.common.instrument_cache import BrokerInstrumentAdapter

if TYPE_CHECKING:
    from brokers.upstox.instruments.definition import UpstoxInstrumentDefinition


class UpstoxInstrumentAdapter(BrokerInstrumentAdapter):
    """Adapter for Upstox instrument caching and symbol resolution."""

    # Canonical to broker exchange mapping
    CANONICAL_TO_BROKER = {
        "NSE": "NSE_EQ",  # Upstox uses NSE_EQ for equity
        "BSE": "BSE_EQ",  # Upstox uses BSE_EQ for equity
        "NFO": "NSE_FO",
        "BFO": "BSE_FO",
        "MCX": "MCX",
        "CDS": "NSE_CDS",
    }

    def __init__(self, db_path):
        self.db_path = db_path

    @property
    def broker_name(self) -> str:
        return "upstox"

    @property
    def table_name(self) -> str:
        return "instruments_upstox"

    def get_schema(self) -> str:
        return """
            CREATE TABLE IF NOT EXISTS instruments_upstox (
                instrument_key TEXT PRIMARY KEY,
                symbol TEXT NOT NULL,
                exchange TEXT NOT NULL,
                exchange_segment TEXT NOT NULL,
                instrument_type TEXT,
                name TEXT,
                isin TEXT,
                trading_symbol TEXT,
                expiry DATE,
                strike REAL,
                option_type TEXT,
                underlying_symbol TEXT,
                lot_size INTEGER,
                tick_size REAL
            )
        """

    def get_indexes(self) -> list[str]:
        return [
            "CREATE INDEX IF NOT EXISTS idx_upstox_symbol_exchange ON instruments_upstox(symbol, exchange_segment)",
            "CREATE INDEX IF NOT EXISTS idx_upstox_name ON instruments_upstox(name)",
            "CREATE INDEX IF NOT EXISTS idx_upstox_isin ON instruments_upstox(isin)",
        ]

    def to_row(self, instrument: "UpstoxInstrumentDefinition") -> dict:
        return {
            "instrument_key": instrument.instrument_key,
            "symbol": instrument.symbol,
            "exchange": instrument.exchange,
            "exchange_segment": instrument.exchange_segment,
            "instrument_type": instrument.instrument_type,
            "name": instrument.name,
            "isin": instrument.isin,
            "trading_symbol": instrument.trading_symbol,
            "expiry": instrument.expiry,
            "strike": instrument.strike,
            "option_type": instrument.option_type,
            "underlying_symbol": instrument.underlying_symbol,
            "lot_size": instrument.lot_size,
            "tick_size": instrument.tick_size,
        }

    def from_row(self, row: dict) -> "UpstoxInstrumentDefinition":
        from brokers.upstox.instruments.definition import UpstoxInstrumentDefinition

        return UpstoxInstrumentDefinition(
            instrument_key=row["instrument_key"],
            exchange=row["exchange"],
            exchange_segment=row["exchange_segment"],
            instrument_type=row.get("instrument_type"),
            name=row.get("name"),
            isin=row.get("isin"),
            trading_symbol=row.get("trading_symbol"),
            expiry=row.get("expiry"),
            strike=row.get("strike"),
            option_type=row.get("option_type"),
            underlying_symbol=row.get("underlying_symbol"),
            lot_size=row.get("lot_size"),
            tick_size=row.get("tick_size"),
        )

    def resolve_symbol(self, symbol: str, exchange: str) -> dict | None:
        """Query SQLite and return raw row for symbol+exchange."""
        # Map canonical exchange to broker-specific exchange
        broker_exchange = self.CANONICAL_TO_BROKER.get(exchange, exchange)

        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(
                """
                SELECT * FROM instruments_upstox
                WHERE symbol = ? AND exchange_segment = ?
                """,
                (symbol, broker_exchange),
            )
            row = cursor.fetchone()
            return dict(row) if row else None

    def build_api_key(self, row: dict) -> str:
        """Build Upstox API key: instrument_key (e.g., 'NSE_EQ|INE002A01018')."""
        return row["instrument_key"]

    def build_api_metadata(self, row: dict) -> dict:
        """Return Upstox-specific metadata."""
        return {
            "exchange_segment": row.get("exchange_segment"),
            "instrument_type": row.get("instrument_type"),
        }
