"""Backward-compat shim — extension providers now live in ``brokers.dhan.extensions.common_extensions``."""
from brokers.dhan.extensions.common_extensions import (  # noqa: F401
    DhanForeverOrderExtension,
    DhanNativeSliceExtension,
    DhanSuperOrderExtension,
    register_dhan_extensions,
)
