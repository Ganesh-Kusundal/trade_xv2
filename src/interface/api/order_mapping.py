"""Pure API → domain enum string mapping for order endpoints."""

from domain.field_mapping import DefaultFieldMapping

# ponytail: SL-M is broker/API wire alias not in DefaultFieldMapping ingest set
_API_ORDER_TYPE_ALIASES = {"SL-M": "STOP_LOSS_MARKET"}


def map_api_order_type(raw: str) -> str:
    """Map API order_type wire values to domain OrderType strings."""
    key = raw.upper()
    if key in _API_ORDER_TYPE_ALIASES:
        return _API_ORDER_TYPE_ALIASES[key]
    return DefaultFieldMapping().map_order_type({"order_type": key})


def map_api_product_type(raw: str) -> str:
    """Map API product_type wire values to domain ProductType strings."""
    key = raw.upper()
    if key == "DELIVERY":
        return "CNC"
    return key
