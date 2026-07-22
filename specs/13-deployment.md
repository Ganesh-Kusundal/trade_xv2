# 13 — Deployment

## 1. Purpose

Deployment specifications cover containerization, orchestration, CI/CD, and release management for production trading operations.

## 2. Containerization

### Multi-Stage Dockerfile

```dockerfile
# Stage 1: Build
FROM python:3.12-slim AS builder
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN pip install uv && uv sync --frozen --no-dev

# Stage 2: Runtime
FROM python:3.12-slim AS runtime
WORKDIR /app
COPY --from=builder /app/.venv /app/.venv
COPY src/ ./src/
ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONPATH="/app/src"

# Non-root user
RUN useradd --create-home tradex
USER tradex

EXPOSE 8080 9090
HEALTHCHECK --interval=30s --timeout=5s \
  CMD curl -f http://localhost:8080/health/live || exit 1

ENTRYPOINT ["tradex"]
CMD ["live", "--config", "/app/config/live.yaml"]
```

### Container Requirements

| Requirement | Specification |
|-------------|---------------|
| Base image | python:3.12-slim |
| User | Non-root (tradex) |
| Health endpoint | /health/live and /health/ready |
| Metrics endpoint | /metrics (Prometheus format) |
| Config mount | /app/config/ (read-only volume) |
| Data mount | /app/data/ (read-write volume) |
| Secrets | Environment variables, never in image |

## 3. Kubernetes Deployment

### Helm Chart Values

```yaml
# charts/tradex/values.yaml
replicaCount: 1                    # Single instance for trading

image:
  repository: tradex
  tag: "1.0.0"
  pullPolicy: IfNotPresent

config:
  environment: LIVE
  broker: dhan
  profile: live.yaml

resources:
  requests:
    cpu: 500m
    memory: 512Mi
  limits:
    cpu: 2000m
    memory: 2Gi

probes:
  liveness:
    path: /health/live
    initialDelaySeconds: 30
    periodSeconds: 30
  readiness:
    path: /health/ready
    initialDelaySeconds: 60
    periodSeconds: 10

persistence:
  enabled: true
  size: 10Gi
  mountPath: /app/data

secrets:
  dhanClientId: ""
  dhanAccessToken: ""
```

### Deployment Constraints

| Constraint | Reason |
|------------|--------|
| replicaCount: 1 | Single trading instance; no concurrent order submission |
| No autoscaling | Trading state is in-memory; scaling requires state externalization |
| Persistent volume | Datalake and token state |
| PodDisruptionBudget: maxUnavailable: 0 | Prevent accidental termination during market hours |

## 4. CI/CD Pipeline

### Pipeline Stages

```yaml
# Pipeline overview
stages:
  - lint          # ruff, mypy, import-linter
  - unit          # domain, FSM, messages
  - component     # OMS, execution, risk
  - architecture  # flow contracts, dependency graph
  - integration   # broker sandbox (nightly)
  - parity        # zero-parity gate
  - build         # Docker image
  - deploy        # staging → production (manual approval)
```

### CI Requirements

| Stage | Blocking | Frequency |
|-------|----------|-----------|
| Lint + Unit + Component + Architecture | Yes | Every push |
| Parity gate | Yes | Every push |
| Integration | Yes | Nightly + pre-release |
| E2E | Yes | Pre-release |
| Docker build | Yes | Every merge to main |
| Deploy staging | No | Automatic on main |
| Deploy production | Yes (manual) | Release tag only |

## 5. Versioning and Release

### Semantic Versioning

```
MAJOR.MINOR.PATCH[-prerelease]

1.0.0-alpha.1   Pre-release
1.0.0-beta.1    Beta
1.0.0-rc.1      Release candidate
1.0.0           Stable
1.1.0           Feature release
2.0.0           Breaking change
```

### Release Checklist

- [ ] All CI stages pass (including parity gate)
- [ ] Four-mode parity gate passes (REPLAY, BACKTEST, PAPER, LIVE)
- [ ] Integration tests pass against broker sandbox
- [ ] E2E replay, backtest, and paper sessions verified
- [ ] CHANGELOG updated
- [ ] Version bumped in pyproject.toml
- [ ] Docker image built and scanned
- [ ] Staging deployment verified
- [ ] Manual approval for production
- [ ] Production deployment during market off-hours
- [ ] Post-deploy reconciliation verified
- [ ] Monitoring dashboards checked

### Post-Deploy Reconciliation (LIVE)

Mandatory gates after every LIVE deployment:

| Gate | Pass Criteria | Failure Action |
|------|---------------|----------------|
| Venue connectivity | Broker adapter connected and authenticated | Roll back deploy; alert operator |
| Position reconciliation | No HIGH-severity drift vs broker | Block order submission; manual review |
| Order reconciliation | No UNKNOWN orders in cache | Reconcile or cancel orphans |
| RiskGate profile | LIVE limits loaded and active | Abort startup |
| Four-mode parity | Parity gate passed in CI for release tag | Block production deploy |
| Audit continuity | Audit sink receiving events | Fail readiness probe |

Production deploy is not complete until all gates pass.

## 6. Environment Separation

| Environment | Infrastructure | Broker | Data |
|-------------|---------------|--------|------|
| Development | Local machine | Paper | Local datalake |
| Staging | K8s staging namespace | Dhan sandbox | Staging datalake |
| Production | K8s production namespace | Dhan/Upstox live | Production datalake |

No production credentials in development or staging environments.

## 7. Secrets Management

| Secret | Storage | Rotation |
|--------|---------|----------|
| Broker API tokens | K8s Secret / env vars | Auto-refresh with cooldown |
| TOTP seeds | K8s Secret | Manual rotation |
| Database credentials | K8s Secret | Quarterly |
| OTLP credentials | K8s Secret | As needed |

Secrets never appear in config files, Docker images, or logs.

## 8. Monitoring in Production

| Monitor | Tool | Alert |
|---------|------|-------|
| Order flow | Prometheus + Grafana | Rejection rate > threshold |
| Latency | Prometheus histograms | p99 > 500ms |
| Broker connectivity | broker_connected gauge | Disconnect > 30s |
| Reconciliation | drift counter | HIGH severity |
| System health | K8s probes | Readiness failure |
| Audit | Append-only log store | Missing audit events |

## 9. Disaster Recovery

| Scenario | Response |
|----------|----------|
| Pod crash | K8s restarts; reconciliation on reconnect |
| Broker API outage | Circuit breaker; queue orders; alert operator |
| Data corruption | Restore from Parquet backup; reconcile |
| Kill switch triggered | Manual reset required; audit review |
| Network partition | UNKNOWN orders; reconcile on reconnect |

### Backup Strategy

| Data | Backup | Frequency |
|------|--------|-----------|
| Datalake Parquet | S3/object storage | Daily |
| Audit logs | Append-only store | Continuous |
| Config | Git repository | On change |
| Token state | Encrypted backup | On refresh |

## 10. Deployment Invariants

1. Single trading instance per account
2. Non-root container user
3. Health probes on every deployment
4. Production deploy requires manual approval
5. Post-deploy reconciliation mandatory
6. No secrets in images or config files
7. Four-mode parity gate passes before any production deploy
