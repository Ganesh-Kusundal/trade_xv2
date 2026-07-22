"""Unit tests for ProcessKernel bootstrap (ADR-0015 / WS-G)."""

from decimal import Decimal

from runtime.bootstrap import bootstrap_platform
from runtime.kernel import ProcessKernel, wire_domain_port_sinks


def test_bootstrap_platform_wires_execution_engine_context():
    session = bootstrap_platform(total_capital=Decimal("500000.00"))

    assert session.trading_context is not None
    assert session.execution_engine is not None
    assert session.execution_engine.order_manager is session.trading_context.order_manager


def test_wire_domain_port_sinks_is_idempotent():
    ProcessKernel.wire()
    ProcessKernel.wire()


def test_process_kernel_wire_reexports_compat():
    wire_domain_port_sinks()
    wire_domain_port_sinks()
