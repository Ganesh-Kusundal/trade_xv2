"""Dhan-specific field name mapping for Order parsing.

Maps DhanHQ API response field names to canonical Order fields.
"""

from brokers.common.core.models import FieldMapping


class DhanFieldMapping:
    """Dhan-specific field name mapping.
    
    Dhan uses camelCase field names like orderId, tradingSymbol,
    exchangeSegment, transactionType, etc.
    """
    
    def map_order_id(self, data: dict) -> str:
        # Support both Dhan (camelCase) and snake_case for backward compatibility
        return str(data.get("orderId", data.get("order_id", "")))
    
    def map_symbol(self, data: dict) -> str:
        # Support both Dhan (camelCase) and snake_case for backward compatibility
        return str(data.get("tradingSymbol", data.get("symbol", "")))
    
    def map_exchange(self, data: dict) -> str:
        # Support both Dhan (camelCase) and snake_case for backward compatibility
        return data.get("exchangeSegment", data.get("exchange", "NSE"))
    
    def map_side(self, data: dict) -> str:
        # Support both Dhan (camelCase) and snake_case for backward compatibility
        return str(data.get("transactionType", data.get("side", "BUY"))).upper()
    
    def map_order_type(self, data: dict) -> str:
        # Support both Dhan (camelCase) and snake_case for backward compatibility
        raw = str(data.get("orderType", data.get("order_type", "MARKET"))).upper()
        aliases = {
            "STOPLOSS_LIMIT": "STOP_LOSS",
            "STOPLOSS_MARKET": "STOP_LOSS_MARKET",
            "STOPLOSS-MARKET": "STOP_LOSS_MARKET",
            "SL": "STOP_LOSS",  # Universal alias
            "SLM": "STOP_LOSS_MARKET",  # Universal alias
        }
        return aliases.get(raw, raw)
    
    def map_status(self, data: dict) -> str:
        # Support both Dhan (camelCase) and snake_case for backward compatibility
        return str(data.get("orderStatus", data.get("status", "OPEN"))).upper()
    
    def map_quantity(self, data: dict) -> int:
        return int(data.get("quantity", 0))
    
    def map_filled_quantity(self, data: dict) -> int:
        # Support both Dhan (camelCase) and snake_case for backward compatibility
        return int(data.get("filledQty", data.get("filled_quantity", 0)))
    
    def map_price(self, data: dict) -> str | None:
        v = data.get("price")
        return None if v in (None, "") else str(v)
    
    def map_avg_price(self, data: dict) -> str | None:
        # Support multiple field names for backward compatibility
        v = data.get("averagePrice", data.get("avg_price", data.get("average_price")))
        return None if v in (None, "") else str(v)
    
    def map_reject_reason(self, data: dict) -> str:
        # Support both Dhan (camelCase) and snake_case for backward compatibility
        return str(data.get("rejectReason", data.get("reject_reason", "")))
