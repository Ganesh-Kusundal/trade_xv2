"""Architecture test: idempotency systems are clearly layered."""
import pytest


@pytest.mark.architecture
def test_oms_idempotency_guard_exists():
    """OMS-level idempotency guard exists."""
    from application.oms.idempotency_guard import IdempotencyGuard
    guard = IdempotencyGuard()
    assert hasattr(guard, 'check_and_reserve')
    assert hasattr(guard, 'release_pending')


@pytest.mark.architecture
def test_broker_idempotency_cache_exists():
    """Broker-level idempotency cache exists."""
    import importlib
    mod = importlib.import_module("brokers.common.idempotency")
    IdempotencyCache = mod.IdempotencyCache
    cache = IdempotencyCache()
    assert hasattr(cache, 'get')
    assert hasattr(cache, 'put')
    assert hasattr(cache, 'reserve')
    assert hasattr(cache, 'commit')


@pytest.mark.architecture
def test_upstox_alias_delegates_to_common():
    """Upstox idempotency is an alias, not a separate implementation."""
    import importlib
    upstox_mod = importlib.import_module("brokers.upstox.orders.idempotency")
    common_mod = importlib.import_module("brokers.common.idempotency")
    assert issubclass(upstox_mod.InMemoryIdempotencyCache, common_mod.IdempotencyCache)


@pytest.mark.architecture
def test_no_new_idempotency_constructors_in_brokers():
    """No new idempotency implementations should be added in broker code."""
    import ast
    from pathlib import Path

    root = Path(__file__).resolve().parents[2] / "src" / "brokers"
    violations = []

    forbidden_classes = {"InMemoryIdempotencyCache", "IdempotencyGuard"}

    for py in root.rglob("*.py"):
        if "common/idempotency" in str(py) or "upstox/orders/idempotency" in str(py):
            continue  # Skip the canonical implementations
        text = py.read_text(errors="ignore")
        try:
            tree = ast.parse(text)
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef) and node.name in forbidden_classes:
                violations.append(f"  {py.relative_to(root.parent.parent)}:{node.lineno}: class {node.name}")

    if violations:
        pytest.fail(
            "New idempotency implementations found in broker code "
            "(use brokers.common.idempotency):\n" + "\n".join(violations)
        )
