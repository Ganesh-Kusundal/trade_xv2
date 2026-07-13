"""OHLCV bar shapes must use domain HistoricalBar as SSOT (ADR-020)."""

from __future__ import annotations

import ast
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SRC = PROJECT_ROOT / "src"

_AGGREGATOR = SRC / "application" / "streaming" / "candle_aggregator.py"
_REPLAY_MODELS = SRC / "analytics" / "replay" / "models.py"
_API_SCHEMAS = SRC / "interface" / "api" / "schemas"
_MARKET_ROUTER = SRC / "interface" / "api" / "routers" / "market.py"
_LIVE_MARKET_ROUTER = SRC / "interface" / "api" / "routers" / "live" / "market.py"
_REQUESTS = SRC / "domain" / "orders" / "requests.py"
_MAPPER = SRC / "interface" / "api" / "candle_mapper.py"

_FORBIDDEN_BAR_CLASSES = {"Bar", "Candle", "HistoricalCandle"}
_ALLOWED_CANDLE_CLASS = {
    ("src/interface/api/schemas/__init__.py", "Candle"),
    ("src/interface/api/schemas/_market.py", "Candle"),
}


def _class_defs(path: Path) -> list[str]:
    if path.is_dir():
        names = []
        for py in sorted(path.glob("*.py")):
            if py.name.startswith("_") and py.name != "__init__.py":
                tree = ast.parse(py.read_text(encoding="utf-8"))
                names.extend(node.name for node in ast.walk(tree) if isinstance(node, ast.ClassDef))
        return names
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return [node.name for node in ast.walk(tree) if isinstance(node, ast.ClassDef)]


def _find_class_definitions(root: Path, class_names: set[str]) -> list[tuple[Path, str]]:
    hits: list[tuple[Path, str]] = []
    for py_file in root.rglob("*.py"):
        rel = str(py_file.relative_to(PROJECT_ROOT))
        if "__pycache__" in rel or "venv" in rel or "/tests/" in rel:
            continue
        try:
            tree = ast.parse(py_file.read_text(encoding="utf-8"), filename=rel)
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef) and node.name in class_names:
                hits.append((py_file, node.name))
    return hits


def test_aggregator_does_not_define_candle_class() -> None:
    """Live aggregation emits domain HistoricalBar, not a parallel Candle type."""
    names = _class_defs(_AGGREGATOR)
    assert "Candle" not in names
    text = _AGGREGATOR.read_text(encoding="utf-8")
    assert "from domain.candles.historical import HistoricalBar" in text
    assert "Candle = HistoricalBar" not in text


def test_replay_uses_domain_historical_bar() -> None:
    """Analytics replay must not define a separate Bar dataclass or alias."""
    names = _class_defs(_REPLAY_MODELS)
    assert "Bar" not in names
    text = _REPLAY_MODELS.read_text(encoding="utf-8")
    assert "from domain.candles.historical import HistoricalBar" in text
    assert "Bar = HistoricalBar" not in text


def test_historical_candle_removed_from_domain() -> None:
    """HistoricalCandle must not exist as a domain class (ADR-020)."""
    names = _class_defs(_REQUESTS)
    assert "HistoricalCandle" not in names
    hits = _find_class_definitions(SRC / "domain", {"HistoricalCandle"})
    assert hits == []


def test_no_parallel_bar_candle_classes_under_src() -> None:
    """Only API schemas may define class Candle; no Bar/HistoricalCandle elsewhere."""
    hits = _find_class_definitions(SRC, _FORBIDDEN_BAR_CLASSES)
    violations = []
    for path, name in hits:
        rel = str(path.relative_to(PROJECT_ROOT))
        if (rel.replace("\\", "/"), name) in _ALLOWED_CANDLE_CLASS:
            continue
        violations.append(f"{rel}:{name}")
    assert not violations, "Parallel OHLCV classes: " + ", ".join(violations)


def test_api_candle_schema_is_wire_only() -> None:
    """REST Candle stays a Pydantic boundary type; mapper references HistoricalBar."""
    names = _class_defs(_API_SCHEMAS)
    assert "Candle" in names
    assert _MAPPER.is_file()
    mapper_text = _MAPPER.read_text(encoding="utf-8")
    assert "HistoricalBar" in mapper_text
    assert "series_to_api_candles" in mapper_text


def test_market_routers_use_series_mapper() -> None:
    """HTTP candle routes must not build Candle(...) inline from raw rows."""
    for path in (_MARKET_ROUTER, _LIVE_MARKET_ROUTER):
        text = path.read_text(encoding="utf-8")
        assert "series_to_api_candles" in text
        assert "Candle(" not in text
