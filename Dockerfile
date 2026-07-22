# syntax=docker/dockerfile:1
# TradeXV2 production API image (R12) — multi-stage, non-root, pip install (not editable).

FROM python:3.12-slim-bookworm AS builder

WORKDIR /build

RUN apt-get update \
    && apt-get install -y --no-install-recommends gcc g++ \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml ./
COPY src ./src

RUN pip install --no-cache-dir .

FROM python:3.12-slim-bookworm AS runtime

RUN useradd --create-home --uid 10001 --shell /usr/sbin/nologin tradex

WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    TRADEX_API_HOST=0.0.0.0 \
    TRADEX_API_PORT=8080 \
    TRADEX_OBSERVABILITY_HOST=0.0.0.0 \
    TRADEX_OBSERVABILITY_PORT=8765 \
    TRADEX_STATE_ROOT=/var/lib/tradex/state \
    TRADEX_PRIMARY_BROKER=paper \
    TRADEX_DEV=1 \
    AUTH_MODE=none \
    SKIP_PARITY_GATE=1

COPY --from=builder /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin
COPY scripts/run_api_server.py scripts/docker_entrypoint.sh ./scripts/

RUN mkdir -p /var/lib/tradex/state/session-recordings /app/data/lake \
    && chown -R tradex:tradex /app /var/lib/tradex \
    && chmod +x /app/scripts/docker_entrypoint.sh

USER tradex

EXPOSE 8080 8765

VOLUME ["/var/lib/tradex/state", "/app/data/lake"]

ENTRYPOINT ["/app/scripts/docker_entrypoint.sh"]
