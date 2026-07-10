"""Capability surface manifest — SSOT for broker → gateway → CLI → REST coverage.

Each :class:`CapabilitySurface` records how a feature is implemented at the
broker layer and whether it is exposed on CLI and REST surfaces.

.. note::
    Architecture debt (tracked, not yet remediated): runtime-discoverable
    capabilities via :class:`domain.extensions.registry.ExtensionRegistry`
    should eventually deprecate the hardcoded ``Capability`` enum in
    :mod:`domain.capabilities`. This package remains the *declarative
    coverage SSOT* (drives ``tests/capability/`` and
    ``scripts/audit/capability_report.py``) and intentionally references the
    ``Capability`` enum for stable IDs.

    It is **not** a behavioral broker-coupling point — it holds no broker
    imports and performs no I/O.
"""

from __future__ import annotations

from domain.capability_manifest.catalog import CAPABILITY_SURFACES
from domain.capability_manifest.query import (
    abc_gateway_methods,
    all_capability_enum_values,
    all_surfaces,
    broker_only_capabilities,
    classify_exposure,
    mapped_capability_values,
    surface_by_id,
    surfaces_for_capability,
)
from domain.capability_manifest.types import (
    BrokerMethodRef,
    CapabilitySurface,
    CliExposure,
    DataSource,
    ExposureStatus,
    RestExposure,
    Severity,
    Tier,
)

__all__ = [
    "CAPABILITY_SURFACES",
    "BrokerMethodRef",
    "CapabilitySurface",
    "CliExposure",
    "DataSource",
    "ExposureStatus",
    "RestExposure",
    "Severity",
    "Tier",
    "abc_gateway_methods",
    "all_capability_enum_values",
    "all_surfaces",
    "broker_only_capabilities",
    "classify_exposure",
    "mapped_capability_values",
    "surface_by_id",
    "surfaces_for_capability",
]
