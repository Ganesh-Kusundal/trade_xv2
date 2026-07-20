"""Architecture test: single configuration source.

Verifies that TradeXV2 has one canonical configuration system (AppConfig in
config.schema) and no duplicate or competing config modules.  This prevents
config proliferation — the kind of design debt that causes inconsistencies
between environments and makes startup behaviour hard to reason about.
"""

from __future__ import annotations

from pathlib import Path

import pytest

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_CONFIG_DIR = _PROJECT_ROOT / "src" / "config"


# ── 1. Main config schema exists and is importable ──────────────────────


@pytest.mark.architecture
def test_config_schema_exists():
    """Main config schema exists and is importable."""
    from config.schema import AppConfig

    assert AppConfig is not None


# ── 2. No duplicate settings modules ─────────────────────────────────────


@pytest.mark.architecture
def test_no_duplicate_settings_modules():
    """No duplicate settings modules should exist inside src/config/.

    The config package may contain focused sub-modules (schema, validator,
    profiles, …) but must NOT contain multiple competing 'settings'
    files that each define their own config loading logic.
    """
    py_files = list(_CONFIG_DIR.glob("*.py"))

    settings_files = [f for f in py_files if "settings" in f.stem.lower()]
    assert len(settings_files) <= 1, (
        f"Multiple settings files found: {[f.name for f in settings_files]}. "
        "There should be at most one settings module; use config.schema.AppConfig."
    )


@pytest.mark.architecture
def test_no_competing_config_in_runtime():
    """src/runtime/ must not contain modules that define a parallel config system.

    Validation helpers (e.g. production_config.validate_production_config)
    are fine — they check config, not define it.  But we should not see
    additional files named like config modules that define their own
    BaseModel / dataclass config classes duplicating config.schema.
    """
    import ast

    runtime_dir = _PROJECT_ROOT / "src" / "runtime"
    if not runtime_dir.is_dir():
        return  # nothing to check

    competing: list[tuple[str, str]] = []  # (file, class_name)
    for py_file in runtime_dir.glob("*config*.py"):
        try:
            tree = ast.parse(py_file.read_text(encoding="utf-8"))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                for base in node.bases:
                    base_name = base.id if isinstance(base, ast.Name) else ""
                    if base_name in ("BaseModel",):
                        competing.append((py_file.name, node.name))

    assert not competing, (
        "Competing config classes found in src/runtime/*config* files: "
        + ", ".join(f"{name} in {fname}" for fname, name in competing)
        + ". All config definitions belong in config.schema."
    )


# ── 3. Config is a structured type, not a plain dict ─────────────────────


@pytest.mark.architecture
def test_config_is_dataclass_or_pydantic():
    """Config should be a structured type (dataclass or Pydantic model)."""
    import dataclasses

    from config.schema import AppConfig

    assert dataclasses.is_dataclass(AppConfig) or hasattr(AppConfig, "model_fields"), (
        "AppConfig must be a dataclass or Pydantic model, not a plain dict"
    )


# ── 4. AppConfig is the canonical central config ─────────────────────────


@pytest.mark.architecture
def test_app_config_is_central():
    """AppConfig must be re-exported from the config package __init__."""
    from config import AppConfig

    assert AppConfig is not None
    assert hasattr(AppConfig, "from_env"), (
        "AppConfig must provide a from_env() class method for env-var loading"
    )


# ── 5. No scattered os.getenv in non-config modules ─────────────────────


@pytest.mark.architecture
def test_feature_flags_module_removed():
    """FeatureFlags subsystem removed; toggles live in config.schema env vars."""
    assert not (_CONFIG_DIR / "feature_flags.py").exists()


@pytest.mark.architecture
def test_no_scattered_env_reads_in_domain():
    """Domain layer must not read env vars directly via os.getenv/os.environ.

    All env-var access should go through config.schema so there is a single
    point of control for defaults, validation, and overrides.
    """
    import ast

    domain_dir = _PROJECT_ROOT / "src" / "domain"
    if not domain_dir.is_dir():
        pytest.skip("src/domain/ does not exist")

    violations: list[tuple[str, int]] = []  # (file, lineno)
    for py_file in domain_dir.rglob("*.py"):
        if "__pycache__" in str(py_file):
            continue
        try:
            tree = ast.parse(py_file.read_text(encoding="utf-8"))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                func = node.func
                # os.getenv(...) or os.environ.get(...)
                if isinstance(func, ast.Attribute) and func.attr in ("getenv", "get"):
                    if (isinstance(func.value, ast.Name) and func.value.id == "os") or (
                        isinstance(func.value, ast.Attribute)
                        and (
                            isinstance(func.value.value, ast.Name)
                            and func.value.value.id == "os"
                            and func.value.attr == "environ"
                        )
                    ):
                        violations.append((str(py_file.relative_to(_PROJECT_ROOT)), node.lineno))

    assert not violations, (
        "Domain layer must not call os.getenv/os.environ.get directly. "
        "Use config.schema instead. Violations:\n"
        + "\n".join(f"  {f}:{ln}" for f, ln in violations)
    )
