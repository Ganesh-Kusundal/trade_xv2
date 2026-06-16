"""Dhan instrument cache adapter."""

from __future__ import annotations

import sqlite3
from typing import TYPE_CHECKING

from brokers.common.instrument_cache import BrokerInstrumentAdapter

if TYPE_CHECKING:
    pass  # Dhan instrument type


class DhanInstrumentAdapter(BrokerInstrumentAdapter):
    """Adapter for Dhan instrument caching and symbol resolution."""

    # Canonical to broker exchange mapping
    CANONICAL_TO_BROKER = {
        "NSE": "NSE",
        "BSE": "BSE",
        "NFO": "NSE_FNO",
        "BFO": "BSE_FNO",
        "MCX": "MCX",
        "CDS": "CDS",
    }

    def __init__(self, db_path):
        self.db_path = db_path

    @property
    def broker_name(self) -> str:
        return "dhan"

    @property
    def table_name(self) -> str:
        return "instruments_dhan"

    def get_schema(self) -> str:
        return """
            CREATE TABLE IF NOT EXISTS instruments_dhan (
                security_id TEXT PRIMARY KEY,
                trading_symbol TEXT NOT NULL,
                exchange TEXT NOT NULL,
                exchange_segment TEXT NOT NULL,
                instrument_name TEXT,
                custom_symbol TEXT,
                symbol_name TEXT,
                expiry DATE,
                strike_price REAL,
                option_type TEXT,
                underlying_security_id TEXT,
                lot_size REAL,
                tick_size REAL
            )
        """

    def get_indexes(self) -> list[str]:
        return [
            "CREATE INDEX IF NOT EXISTS idx_dhan_trading_symbol ON instruments_dhan(trading_symbol, exchange_segment)",
            "CREATE INDEX IF NOT EXISTS idx_dhan_custom_symbol ON instruments_dhan(custom_symbol)",
            "CREATE INDEX IF NOT EXISTS idx_dhan_symbol_name ON instruments_dhan(symbol_name)",
        ]

    def to_row(self, instrument: dict) -> dict:
        """Convert Dhan instrument dict to SQLite row."""
        return {
            "security_id": instrument.get("security_id"),
            "trading_symbol": instrument.get("trading_symbol"),
            "exchange": instrument.get("exchange"),
            "exchange_segment": instrument.get("exchange_segment"),
            "instrument_name": instrument.get("instrument_name"),
            "custom_symbol": instrument.get("custom_symbol"),
            "symbol_name": instrument.get("symbol_name"),
            "expiry": instrument.get("expiry"),
            "strike_price": instrument.get("strike_price"),
            "option_type": instrument.get("option_type"),
            "underlying_security_id": instrument.get("underlying_security_id"),
            "lot_size": instrument.get("lot_size"),
            "tick_size": instrument.get("tick_size"),
        }

    def from_row(self, row: dict) -> dict:
        """Convert SQLite row back to Dhan instrument dict."""
        return {
            "security_id": row["security_id"],
            "trading_symbol": row["trading_symbol"],
            "exchange": row["exchange"],
            "exchange_segment": row["exchange_segment"],
            "instrument_name": row.get("instrument_name"),
            "custom_symbol": row.get("custom_symbol"),
            "symbol_name": row.get("symbol_name"),
            "expiry": row.get("expiry"),
            "strike_price": row.get("strike_price"),
            "option_type": row.get("option_type"),
            "underlying_security_id": row.get("underlying_security_id"),
            "lot_size": row.get("lot_size"),
            "tick_size": row.get("tick_size"),
        }

    def resolve_symbol(self, symbol: str, exchange: str) -> dict | None:
        """Query SQLite and return raw row for symbol+exchange."""
        # Map canonical exchange to broker-specific exchange
        broker_exchange = self.CANONICAL_TO_BROKER.get(exchange, exchange)

        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(
                """
                SELECT * FROM instruments_dhan
                WHERE trading_symbol = ? AND exchange_segment = ?
                """,
                (symbol, broker_exchange),
            )
            row = cursor.fetchone()
            return dict(row) if row else None

    def build_api_key(self, row: dict) -> str:
        """Build Dhan API key: security_id (e.g., '1333')."""
        return str(row["security_id"])

    def build_api_metadata(self, row: dict) -> dict:
        """Return Dhan-specific metadata."""
        return {
            "exchange_segment": row.get("exchange_segment"),
        }
