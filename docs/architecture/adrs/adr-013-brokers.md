# ADR-013: Supported Broker Set

- **Status:** Accepted
- **Date:** 2026-07-10
- **Deciders:** Chief Quant Architect, Broker Platform Division

## Context

The proposed Trading OS diagram listed four brokers: Dhan, Upstox, Zerodha, and
a Paper Broker. The implemented `Trade_XV2` codebase provides broker plugins
for **Dhan, Upstox, Paper, and Datalake** — Zerodha is not implemented.

## Decision

- The canonical broker set is: **Dhan, Upstox, Paper, Datalake**.
- **Zerodha is dropped** from the architecture diagram and documentation. It may
  be added later as a new `BrokerPlugin` + adapter following the existing
  plugin pattern, but it is not part of the supported set today.
- `Paper` and `Datalake` are explicitly **non-live** (`is_live=False`); only
  Dhan and Upstox are live execution brokers.

## Consequences

- Documentation and diagrams now match the code (no phantom broker).
- Future Zerodha support is a contained Broker Platform Division task using the
  existing `BrokerPlugin` self-registration pattern in
  `infrastructure/broker_plugin.py`.
