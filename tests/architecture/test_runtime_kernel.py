"""ADR-0015 — RuntimeKernel is the sole composition root; ApplicationContainer removed."""

from __future__ import annotations

import pytest


@pytest.mark.architecture
def test_application_container_removed() -> None:
    with pytest.raises(ModuleNotFoundError):
        import runtime.container  # noqa: F401


@pytest.mark.architecture
def test_runtime_kernel_exports_bootstrap_and_wire() -> None:
    from runtime import kernel

    assert callable(kernel.bootstrap_platform)
    assert callable(kernel.ProcessKernel.wire)
    assert callable(kernel.ProcessKernel.boot)
    assert callable(kernel.wire_domain_port_sinks)
    assert callable(kernel.build_from_broker_service)
