# ADR-012-DEPLOY: Docker/K8s Deployment Architecture

## Status

Proposed

## Context

The trading platform needs a deployment model that supports:

- **Local development** — single-process, all components in one Python process.
- **Staging** — containerized deployment with separate API, worker, and UI processes.
- **Production** — Kubernetes-orchestrated with health checks, auto-scaling, and rolling updates.

The current deployment is local-only (`tradex.Session` / `runtime.factory.build`). A formal deployment architecture is needed to support team growth and production reliability.

## Decision

### Container Architecture

```yaml
# Proposed container layout
services:
  api:           # FastAPI REST API (interface/api/)
    ports: [8000]
    health: /health
  worker:        # Trading worker (application/trading/ + application/oms/)
    replicas: 1  # Single writer for order book consistency
    health: /health
  ui:            # Streamlit/Tauri UI (interface/ui/)
    ports: [8501]
  analytics:     # DuckDB analytics queries (analytics/)
    ports: [8002]
  datafeed:      # Market data feed handler (application/streaming/)
    replicas: 1
```

### Deployment Constraints

1. **Order book singleton:** The OMS worker must run as a single replica (SQLite is single-writer). Multi-worker deployment requires PostgreSQL migration (deferred per ADR-014).
2. **Event bus:** In-process EventBus is single-process. Cross-process event routing requires Redis/NATS (deferred).
3. **Shared storage:** Parquet data lake must be on shared storage (NFS/S3) for multi-container access.

### Container Registry

- Images built via `Dockerfile` (multi-stage: builder → runtime).
- Images tagged with `git-sha` for traceability.
- Published to internal registry (ECR/GCR).

## Consequences

**Positive:**
- Consistent deployment across environments.
- Health checks enable Kubernetes self-healing.
- Container isolation prevents resource contention.

**Negative:**
- Container overhead (~50MB base image).
- SQLite single-writer constraint limits horizontal scaling.
- EventBus in-process model requires refactoring for cross-container communication.

## Enforcement

- `Dockerfile` in project root (to be created)
- `docker-compose.yml` for local development
- `k8s/` manifests for Kubernetes deployment
- **NEW:** `tests/architecture/test_deployment_manifests.py` (proposed)
