"""REF-12: Verify no module-level __getattr__ re-exports remain."""
import ast
import pathlib


def test_no_module_level_getattr_reexports():
    """Scan src/ for module-level __getattr__ that do re-exports.

    Class-level __getattr__ (facade pattern) is allowed.
    Intentional circular-import guards are excluded via the allowlist.
    """
    src = pathlib.Path("src")
    violations = []
    for py in src.rglob("*.py"):
        if "__pycache__" in str(py) or "tests" in str(py):
            continue
        try:
            tree = ast.parse(py.read_text())
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == "__getattr__":
                # Check if at module level (not inside a class)
                # Heuristic: if the function's col_offset is 0, it's module-level
                if node.col_offset == 0:
                    violations.append(str(py))

    # Allow known exceptions:
    # - brokers/__init__.py: circular-import guard (documented)
    # - brokers/providers/dhan/domain.py: circular-import guard (documented)
    # - domain/instruments/instrument.py: circular-import guard (documented)
    # - domain/universe.py: circular-import guard (documented)
    # - domain/extensions/facade.py: class-level facade pattern
    # - infrastructure/event_bus/async_event_bus.py: class-level proxy
    # - application/research/__init__.py: class-level proxy
    allowed = {
        "brokers/__init__.py",
        "brokers/providers/dhan/domain.py",
        "domain/instruments/instrument.py",
        "domain/universe.py",
        "domain/extensions/facade.py",
        "infrastructure/event_bus/async_event_bus.py",
        "application/research/__init__.py",
    }
    violations = [v for v in violations if not any(a in v for a in allowed)]
    assert violations == [], f"Module-level __getattr__ re-exports found: {violations}"
