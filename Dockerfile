# Multi-stage build for TradeXV2
# Stage 1: Build dependencies
# Stage 2: Production runtime

FROM python:3.13-slim AS builder

WORKDIR /build

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Copy dependency files
COPY pyproject.toml ./
COPY requirements*.txt ./

# Install dependencies into a virtual environment
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Install project dependencies
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -e .

# Stage 2: Production image
FROM python:3.13-slim AS production

LABEL maintainer="TradeXV2 Team"
LABEL description="Broker-agnostic algorithmic trading framework for Indian exchanges"

# Create non-root user
RUN groupadd -r tradex && useradd -r -g tradex -m tradex

WORKDIR /app

# Copy virtual environment from builder
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

# Install runtime system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy application code
COPY --chown=tradex:tradex . .

# Switch to non-root user
USER tradex

# Expose ports
# 8000: FastAPI application
# 8765: Observability server (health/metrics)
EXPOSE 8000 8765

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8765/healthz || exit 1

# Default command: run the API server
CMD ["python", "-m", "uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
