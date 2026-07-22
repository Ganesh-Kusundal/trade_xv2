"""Unit tests for FundAllocator capital pools, margin checks, and order slicing."""

from decimal import Decimal
import pytest
from application.portfolio.fund_allocator import FundAllocator, InsufficientCapitalError, SliceManager


def test_fund_allocator_capital_pool_allocation_and_lock():
    allocator = FundAllocator(total_capital=Decimal("1000000.00"))
    
    # Allocate 200,000 to Strategy A
    allocator.allocate_strategy_pool("StratA", Decimal("200000.00"))
    assert allocator.get_available_capital("StratA") == Decimal("200000.00")

    # Reserve 50,000 margin for an open order
    assert allocator.reserve_margin("StratA", Decimal("50000.00")) is True
    assert allocator.get_available_capital("StratA") == Decimal("150000.00")

    # Attempt to reserve 180,000 (exceeds remaining 150,000)
    with pytest.raises(InsufficientCapitalError):
        allocator.reserve_margin("StratA", Decimal("180000.00"))


def test_order_slicing_engine_nse_fno_freeze_limit():
    slicer = SliceManager(max_freeze_quantity=1800)

    # Order of 5,000 contracts should slice into [1800, 1800, 1400]
    slices = slicer.slice_quantity(5000)
    assert len(slices) == 3
    assert slices == [1800, 1800, 1400]
    assert sum(slices) == 5000


def test_order_slicing_engine_small_order_no_slice():
    slicer = SliceManager(max_freeze_quantity=1800)
    slices = slicer.slice_quantity(500)
    assert slices == [500]
