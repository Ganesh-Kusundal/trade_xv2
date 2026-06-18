"""Upstox-specific field name mapping for Order parsing.

Maps Upstox API response field names to canonical Order fields.
"""

from brokers.common.core.models import FieldMapping


class UpstoxFieldMapping:
    """Upstox-specific field name mapping.
    
    Upstox uses snake_case field names like order_id, symbol,
    exchange, side, order_type, status, etc.
    """
    
    def map_order_id(self, data: dict) -> str:
        return str(data.get("order_id", ""))
    
    def map_symbol(self, data: dict) -> str:
        return str(data.get("symbol", ""))
    
    def map_exchange(self, data: dict) -> str:
        return data.get("exchange", "NSE")
    
    def map_side(self, data: dict) -> str:
        return str(data.get("side", "BUY")).upper()
    
    def map_order_type(self, data: dict) -> str:
        raw = str(data.get("order_type", "MARKET")).upper()
        aliases = {
            "SL": "STOP_LOSS",
            "SLM": "STOP_LOSS_MARKET",
        }
        return aliases.get(raw, raw)
    
    def map_status(self, data: dict) -> str:
        return str(data.get("status", "OPEN")).upper()
    
    def map_quantity(self, data: dict) -> int:
        return int(data.get("quantity", 0))
    
    def map_filled_quantity(self, data: dict) -> int:
        return int(data.get("filled_quantity", 0))
    
    def map_price(self, data: dict) -> str | None:
        v = data.get("price")
        return None if v in (None, "") else str(v)
    
    def map_avg_price(self, data: dict) -> str | None:
        v = data.get("avg_price", data.get("average_price"))
        return None if v in (None, "") else str(v)
    
    def map_reject_reason(self, data: dict) -> str:
        return str(data.get("reject_reason", ""))
