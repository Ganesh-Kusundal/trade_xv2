"""Tests for the ResilienceConfig kernel dependency (ADR-012 appendix, P4)."""

from __future__ import annotations

from runtime.resilience import ResilienceConfig


def test_defaults_are_sane() -> None:
    cfg = ResilienceConfig()
    assert cfg.idempotency_backend == "memory"
    assert cfg.dead_letter_enabled is True
    assert cfg.event_log_enabled is True
    assert cfg.parity_gate_enabled is True
    assert cfg.max_async_bus_queue == 10_000


def test_from_env_honors_overrides(monkeypatch) -> None:
    monkeypatch.setenv("TRADEX_IDEMPOTENCY_TTL", "3600")
    monkeypatch.setenv("TRADEX_IDEMPOTENCY_BACKEND", "redis")
    monkeypatch.setenv("SKIP_PARITY_GATE", "1")
    cfg = ResilienceConfig.from_env()
    assert cfg.idempotency_ttl_seconds == 3600
    assert cfg.idempotency_backend == "redis"
    # parity gate disabled when SKIP_PARITY_GATE=1
    assert cfg.parity_gate_enabled is False


def test_from_env_explicit_override_wins(monkeypatch) -> None:
    monkeypatch.setenv("TRADEX_IDEMPOTENCY_BACKEND", "file")
    cfg = ResilienceConfig.from_env(idempotency_backend="memory")
    assert cfg.idempotency_backend == "memory"
