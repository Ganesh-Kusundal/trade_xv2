# 12 — Deployment & CI/CD

## 1. Overview

TradeXV2 uses a modern CI/CD pipeline with GitHub Actions, Docker containers,
and Kubernetes deployment. The pipeline enforces code quality, import-linter
contracts, and comprehensive testing before deployment.

```
┌─────────────────────────────────────────────────────────────┐
│                    CI/CD Pipeline                           │
│                                                             │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐   │
│  │  Lint    │  │  Test    │  │  Build   │  │  Deploy  │   │
│  │  + Type  │  │  Suite   │  │  Docker  │  │  K8s     │   │
│  └──────────┘  └──────────┘  └──────────┘  └──────────┘   │
└─────────────────────────────────────────────────────────────┘
```

## 2. GitHub Actions Workflow

```yaml
# .github/workflows/ci.yml

name: CI/CD

on:
  push:
    branches: [main, develop]
  pull_request:
    branches: [main]

jobs:
  # ── Lint & Type Check ──────────────────────────────────────
  lint:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
      - uses: astral-sh/setup-uv@v3

      - name: Install dependencies
        run: uv sync --dev

      - name: Ruff lint
        run: uv run ruff check src/

      - name: Ruff format check
        run: uv run ruff format --check src/

      - name: Mypy type check
        run: uv run mypy src/

      - name: Import-linter
        run: uv run lint-imports

  # ── Test Suite ─────────────────────────────────────────────
  test:
    runs-on: ubuntu-latest
    strategy:
      matrix:
        python-version: ["3.11", "3.12"]

    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: ${{ matrix.python-version }}
      - uses: astral-sh/setup-uv@v3

      - name: Install dependencies
        run: uv sync --dev

      - name: Run unit tests
        run: uv run pytest tests/unit -v --cov=src --cov-report=xml

      - name: Run integration tests
        run: uv run pytest tests/integration -v

      - name: Upload coverage
        uses: codecov/codecov-action@v4
        with:
          file: ./coverage.xml

  # ── Build ──────────────────────────────────────────────────
  build:
    needs: [lint, test]
    runs-on: ubuntu-latest
    if: github.ref == 'refs/heads/main'

    steps:
      - uses: actions/checkout@v4

      - name: Set up Docker Buildx
        uses: docker/setup-buildx-action@v3

      - name: Login to Container Registry
        uses: docker/login-action@v3
        with:
          registry: ghcr.io
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}

      - name: Build and push
        uses: docker/build-push-action@v5
        with:
          context: .
          push: true
          tags: |
            ghcr.io/${{ github.repository }}:latest
            ghcr.io/${{ github.repository }}:${{ github.sha }}
          cache-from: type=gha
          cache-to: type=gha,mode=max

  # ── Deploy ─────────────────────────────────────────────────
  deploy:
    needs: [build]
    runs-on: ubuntu-latest
    if: github.ref == 'refs/heads/main'

    steps:
      - uses: actions/checkout@v4

      - name: Set up kubectl
        uses: azure/setup-kubectl@v3

      - name: Configure kubectl
        uses: azure/k8s-set-context@v3
        with:
          method: kubeconfig
          kubeconfig: ${{ secrets.KUBE_CONFIG }}

      - name: Deploy to Kubernetes
        run: |
          kubectl set image deployment/tradex \
            tradex=ghcr.io/${{ github.repository }}:${{ github.sha }} \
            -n tradex-prod
          kubectl rollout status deployment/tradex -n tradex-prod
```

## 3. Docker Configuration

```dockerfile
# Dockerfile

FROM python:3.11-slim as base

# Install system dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

# Copy dependency files
COPY pyproject.toml uv.lock ./

# Install dependencies
RUN uv sync --frozen --no-dev

# Copy application code
COPY src/ src/
COPY config/ config/

# Set environment
ENV PYTHONPATH=/app/src
ENV PYTHONUNBUFFERED=1

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import requests; requests.get('http://localhost:8000/health')"

# Run application
CMD ["uv", "run", "python", "-m", "runtime.bootstrap"]
```

```dockerfile
# Dockerfile.dev (for development)

FROM python:3.11-slim

RUN apt-get update && apt-get install -y \
    build-essential \
    git \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

COPY pyproject.toml uv.lock ./
RUN uv sync --dev

COPY . .

ENV PYTHONPATH=/app/src
ENV PYTHONUNBUFFERED=1

CMD ["uv", "run", "python", "-m", "runtime.bootstrap", "--profile", "paper"]
```

## 4. Kubernetes Manifests

```yaml
# k8s/deployment.yaml

apiVersion: apps/v1
kind: Deployment
metadata:
  name: tradex
  namespace: tradex-prod
spec:
  replicas: 2
  selector:
    matchLabels:
      app: tradex
  template:
    metadata:
      labels:
        app: tradex
    spec:
      containers:
      - name: tradex
        image: ghcr.io/tradex/tradex:latest
        ports:
        - containerPort: 8000
          name: http
        - containerPort: 9090
          name: metrics
        env:
        - name: TRADEX_APP__MODE
          value: "live"
        - name: TRADEX_BROKER__ID
          value: "dhan"
        envFrom:
        - secretRef:
            name: tradex-secrets
        resources:
          requests:
            cpu: "500m"
            memory: "1Gi"
          limits:
            cpu: "2000m"
            memory: "4Gi"
        livenessProbe:
          httpGet:
            path: /health
            port: 8000
          initialDelaySeconds: 30
          periodSeconds: 10
        readinessProbe:
          httpGet:
            path: /health
            port: 8000
          initialDelaySeconds: 5
          periodSeconds: 5
        volumeMounts:
        - name: datalake
          mountPath: /data/datalake
      volumes:
      - name: datalake
        persistentVolumeClaim:
          claimName: tradex-datalake
```

```yaml
# k8s/service.yaml

apiVersion: v1
kind: Service
metadata:
  name: tradex
  namespace: tradex-prod
spec:
  selector:
    app: tradex
  ports:
  - name: http
    port: 8000
    targetPort: 8000
  - name: metrics
    port: 9090
    targetPort: 9090
  type: ClusterIP
```

```yaml
# k8s/pvc.yaml

apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: tradex-datalake
  namespace: tradex-prod
spec:
  accessModes:
    - ReadWriteOnce
  resources:
    requests:
      storage: 50Gi
  storageClassName: standard
```

## 5. Makefile

```makefile
# Makefile

.PHONY: help install dev test lint format build run clean

help:  ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

install:  ## Install production dependencies
	uv sync --frozen

dev:  ## Install development dependencies
	uv sync --dev

test:  ## Run test suite
	uv run pytest tests/ -v

test-unit:  ## Run unit tests only
	uv run pytest tests/unit -v --cov=src

test-integration:  ## Run integration tests only
	uv run pytest tests/integration -v

lint:  ## Run linters
	uv run ruff check src/
	uv run mypy src/
	uv run lint-imports

format:  ## Format code
	uv run ruff format src/
	uv run ruff check --fix src/

build:  ## Build Docker image
	docker build -t tradex:latest .

run:  ## Run application (paper mode)
	uv run python -m runtime.bootstrap --profile paper

run-live:  ## Run application (live mode)
	uv run python -m runtime.bootstrap --profile live

backtest:  ## Run backtest
	uv run python -m runtime.bootstrap --profile backtest

clean:  ## Clean build artifacts
	rm -rf .mypy_cache .pytest_cache .ruff_cache dist build *.egg-info
	find . -type d -name __pycache__ -exec rm -rf {} +

docker-run:  ## Run Docker container
	docker run -it --rm -p 8000:8000 -p 9090:9090 tradex:latest

docker-push:  ## Push Docker image
	docker push ghcr.io/tradex/tradex:latest

k8s-deploy:  ## Deploy to Kubernetes
	kubectl apply -f k8s/
	kubectl set image deployment/tradex tradex=ghcr.io/tradex/tradex:latest -n tradex-prod
```

## 6. Environment Secrets

```yaml
# k8s/secrets.yaml (template)

apiVersion: v1
kind: Secret
metadata:
  name: tradex-secrets
  namespace: tradex-prod
type: Opaque
stringData:
  DHAN_ACCESS_TOKEN: "${DHAN_ACCESS_TOKEN}"
  DHAN_CLIENT_ID: "${DHAN_CLIENT_ID}"
  UPSTOX_ACCESS_TOKEN: "${UPSTOX_ACCESS_TOKEN}"
  UPSTOX_CLIENT_ID: "${UPSTOX_CLIENT_ID}"
  UPSTOX_CLIENT_SECRET: "${UPSTOX_CLIENT_SECRET}"
```

## 7. Monitoring Stack

```yaml
# docker-compose.monitoring.yml

version: "3.8"

services:
  prometheus:
    image: prom/prometheus:latest
    ports:
      - "9090:9090"
    volumes:
      - ./monitoring/prometheus.yml:/etc/prometheus/prometheus.yml
      - prometheus_data:/prometheus

  grafana:
    image: grafana/grafana:latest
    ports:
      - "3000:3000"
    environment:
      - GF_SECURITY_ADMIN_PASSWORD=admin
    volumes:
      - grafana_data:/var/lib/grafana
      - ./monitoring/grafana/dashboards:/etc/grafana/provisioning/dashboards

  loki:
    image: grafana/loki:latest
    ports:
      - "3100:3100"
    volumes:
      - loki_data:/loki

volumes:
  prometheus_data:
  grafana_data:
  loki_data:
```

```yaml
# monitoring/prometheus.yml

global:
  scrape_interval: 15s

scrape_configs:
  - job_name: "tradex"
    static_configs:
      - targets: ["tradex:9090"]
    metrics_path: "/metrics"
```

## 8. Comparison with Current State

| Aspect | Current | Target |
|---|---|---|
| CI | Basic GitHub Actions | Full pipeline: lint + test + build + deploy |
| Import-linter | Not enforced | CI-blocking contract checks |
| Docker | None | Multi-stage Dockerfile |
| Kubernetes | None | Production-ready manifests |
| Monitoring | None | Prometheus + Grafana + Loki |
| Secrets | `.env` files | Kubernetes secrets |
| Makefile | Basic | Comprehensive task runner |
