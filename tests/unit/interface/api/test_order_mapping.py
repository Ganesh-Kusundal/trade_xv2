"""Unit tests for API order enum mapping."""

from interface.api.order_mapping import map_api_order_type, map_api_product_type


def test_map_api_order_type_sl():
    assert map_api_order_type("SL") == "STOP_LOSS"


def test_map_api_order_type_sl_m():
    assert map_api_order_type("SL-M") == "STOP_LOSS_MARKET"


def test_map_api_order_type_market_passthrough():
    assert map_api_order_type("MARKET") == "MARKET"
    assert map_api_order_type("market") == "MARKET"


def test_map_api_product_type_delivery():
    assert map_api_product_type("DELIVERY") == "CNC"


def test_map_api_product_type_intraday_passthrough():
    assert map_api_product_type("INTRADAY") == "INTRADAY"
