"""Health registry."""

from infrastructure.observability.health import ComponentHealth, HealthRegistry


def test_registry_stores_health() -> None:
    reg = HealthRegistry()
    h = ComponentHealth(
        component_id="message_bus",
        state="RUNNING",
        metrics={"queue_depth": 0},
    )
    reg.update(h)
    assert reg.get("message_bus") == h
