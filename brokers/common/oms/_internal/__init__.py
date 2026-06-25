"""Shim — use :mod:`application.oms._internal`.

NOTE: PositionManager and create_trading_context are NOT part of
_internal — they live in application.oms directly. Import them from
there instead:

    from application.oms import PositionManager
    from application.oms.factory import create_trading_context
"""
