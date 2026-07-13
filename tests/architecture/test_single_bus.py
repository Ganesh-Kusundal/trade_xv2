"""Architecture test: only one concrete EventBus in runtime wiring."""
import pytest


@pytest.mark.architecture
def test_canonical_event_bus_is_infrastructure():
    """The canonical EventBus must be infrastructure.event_bus.event_bus.EventBus."""
    from infrastructure.event_bus.event_bus import EventBus
    assert EventBus is not None
    assert hasattr(EventBus, 'publish')
    assert hasattr(EventBus, 'subscribe')
    assert hasattr(EventBus, 'unsubscribe')


@pytest.mark.architecture
def test_event_bus_port_is_canonical_protocol():
    """EventBusPort Protocol (domain.ports.event_publisher) is the canonical port."""
    from domain.ports.event_publisher import EventBusPort
    from typing import Protocol
    assert issubclass(EventBusPort, Protocol)


@pytest.mark.architecture
def test_no_duplicate_bus_construction_in_application():
    """Application code should not construct its own EventBus instances."""
    import ast
    from pathlib import Path

    root = Path(__file__).resolve().parents[2] / "src" / "application"
    violations = []

    for py in root.rglob("*.py"):
        text = py.read_text(errors="ignore")
        try:
            tree = ast.parse(text)
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                func = node.func
                name = ""
                if isinstance(func, ast.Name):
                    name = func.id
                elif isinstance(func, ast.Attribute):
                    name = func.attr
                if name in ("EventBus", "AsyncEventBus") and "event_bus" not in py.name:
                    violations.append(f"  {py.relative_to(root.parent.parent)}:{node.lineno}: {name}()")

    if violations:
        pytest.fail(
            "Application code should not construct EventBus directly "
            "(inject via composition root):\n" + "\n".join(violations)
        )
