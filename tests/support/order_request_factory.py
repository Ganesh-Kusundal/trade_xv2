def make_order_request(**kwargs):
    """Build OrderRequest from legacy kwargs used in broker unit tests."""
    from decimal import Decimal
    from domain.enums import OrderType, ProductType, Side, Validity
    from domain.orders.requests import OrderRequest

    side = kwargs.get("side", "BUY")
    if not isinstance(side, Side):
        side = Side(str(side).upper())
    ot = kwargs.get("order_type", "MARKET")
    if not isinstance(ot, OrderType):
        ot = OrderType(str(ot).upper())
    pt = kwargs.get("product_type", "INTRADAY")
    if not isinstance(pt, ProductType):
        pt = ProductType(str(pt).upper())
    price = kwargs.get("price", Decimal("0"))
    if price is None:
        price = Decimal("0")
    elif not isinstance(price, Decimal):
        price = Decimal(str(price))
    return OrderRequest(
        symbol=str(kwargs.get("symbol", "")),
        exchange=str(kwargs.get("exchange", "NSE")),
        transaction_type=side,
        quantity=int(kwargs.get("quantity", 1)),
        price=price,
        order_type=ot,
        product_type=pt,
        trigger_price=kwargs.get("trigger_price"),
        validity=Validity.DAY,
        correlation_id=kwargs.get("correlation_id"),
        disclosed_quantity=kwargs.get("disclosed_quantity"),
    )

__all__ = ["make_order_request"]
