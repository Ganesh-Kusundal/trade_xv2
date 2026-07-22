# Multi-stage TradeX V2 image (python 3.12-slim, non-root).
FROM python:3.12-slim AS builder
WORKDIR /build
RUN apt-get update && apt-get install -y --no-install-recommends gcc \
    && rm -rf /var/lib/apt/lists/*
COPY pyproject.toml ./
COPY src/ ./src/
COPY config/ ./config/
RUN pip install --no-cache-dir --prefix=/install .

FROM python:3.12-slim AS runtime
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --uid 1000 tradex
COPY --from=builder /install /usr/local
COPY --chown=tradex:tradex config/ ./config/
COPY --chown=tradex:tradex src/ ./src/
ENV PYTHONPATH=/app/src \
    PATH="/usr/local/bin:$PATH" \
    TRADEX_STATE_ROOT=/app/data
RUN mkdir -p /app/data && chown tradex:tradex /app/data
USER tradex
EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD curl -fsS http://127.0.0.1:8080/health/live || exit 1
ENTRYPOINT ["tradex"]
CMD ["version"]
