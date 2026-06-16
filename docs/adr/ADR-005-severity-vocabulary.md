# ADR-005: HIGH/MEDIUM/LOW is the Canonical Severity Scale

## Context
Reconciliation drift items used two different severity vocabularies: Dhan used "HIGH"/"MEDIUM"/"LOW" while Upstox used "critical"/"warning". The `ReconciliationReport.high_severity_count` property had to check both.

## Decision
- Canonical severity values are: "HIGH", "MEDIUM", "LOW"
- All broker reconciliation adapters emit these values
- `ReconciliationReport.high_severity_count` checks only `severity == "HIGH"`

## Consequences
- Consistent severity across all brokers
- Simpler property implementation
- Alerting rules can rely on a single vocabulary
