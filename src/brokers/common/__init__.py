"""Broker-agnostic residual modules (not a re-export layer).

Canonical homes
---------------
- Ports / protocols: ``domain.ports`` (``BrokerAdapter``, ``DataProvider``, …)
- Platform kernel: ``tradex.runtime`` (factory, resilience, auth, services, …)
- Domain types: ``domain``

What remains here
-----------------
- ``broker_capabilities`` — thin re-export of ``domain.capabilities.broker_capabilities``
- ``api`` — broker SPI / margin contracts
- ``oms.margin_provider`` — margin adapter (OMS itself is ``application.oms``)
- ``contracts`` / ``tests`` — cross-broker contract and certification suites

Do not add new re-export shims. Prefer importing from the canonical modules above.
"""
