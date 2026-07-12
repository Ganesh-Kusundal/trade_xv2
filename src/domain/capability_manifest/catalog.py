"""Declarative capability catalog (coverage SSOT).

Data only — types and query helpers live in sibling modules.
Each section of the CAPABILITY_SURFACES tuple lives in its own module
for LOC compliance; this file re-exports the combined tuple.
"""

from __future__ import annotations

from domain.capability_manifest._api_surfaces import API_PRODUCT_SURFACES, MONITORING_SURFACES
from domain.capability_manifest._capability_surfaces import CAPABILITY_ENUM_SURFACES
from domain.capability_manifest._core_surfaces import CORE_SURFACES
from domain.capability_manifest._extended_surfaces import EXTENDED_SURFACES
from domain.capability_manifest._order_surfaces import ORDER_SURFACES

CAPABILITY_SURFACES = (
    *CORE_SURFACES,
    *ORDER_SURFACES,
    *EXTENDED_SURFACES,
    *CAPABILITY_ENUM_SURFACES,
    *MONITORING_SURFACES,
    *API_PRODUCT_SURFACES,
)
