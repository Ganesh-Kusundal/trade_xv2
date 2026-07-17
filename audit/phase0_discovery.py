"""
PHASE 0 — SYSTEM DISCOVERY
Proves entry points, bootstrap sequence, and dependency graph exist at runtime.
FAIL FAST on any import failure.
"""
import sys
import importlib
import inspect

REQUIRED_ENTRY_POINTS = {
    "backend_api":      "interface.api.main",
    "frontend_cli":     "interface.ui.main",
    "runtime_factory":  "runtime.factory",
    "event_bus":        "infrastructure.event_bus.event_bus",
    "trading_context":  "application.oms.context",
    "order_manager":    "application.oms.order_manager",
    "risk_manager":     "application.oms._internal.risk_manager",
    "position_manager": "application.oms.position_manager",
    "feature_builder":  "analytics.core.feature_builder",
    "strategy_pipeline":"analytics.strategy.pipeline",
    "event_types":      "domain.events.types",
}

REQUIRED_CLASSES = {
    "interface.api.main":                     "create_app",
    "infrastructure.event_bus.event_bus":     "EventBus",
    "application.oms.context":                "TradingContext",
    "application.oms.order_manager":          "OrderManager",
    "application.oms._internal.risk_manager": "RiskManager",
    "application.oms.position_manager":       "PositionManager",
    "analytics.core.feature_builder":         "FeatureBuilder",
    "analytics.strategy.pipeline":            "StrategyPipeline",
    "domain.events.types":                    "DomainEvent",
}

def run():
    print("=" * 70)
    print("PHASE 0 — SYSTEM DISCOVERY")
    print("=" * 70)
    failed = []

    for label, mod_path in REQUIRED_ENTRY_POINTS.items():
        try:
            mod = importlib.import_module(mod_path)
            print(f"  [OK]  {label:30s} -> {mod_path}")
        except ImportError as exc:
            print(f"  [FAIL] {label:30s} -> {mod_path}  ERROR: {exc}")
            failed.append((label, mod_path, str(exc)))

    print()
    for mod_path, cls_name in REQUIRED_CLASSES.items():
        try:
            mod = importlib.import_module(mod_path)
            cls = getattr(mod, cls_name)
            src = inspect.getfile(cls) if inspect.isclass(cls) or callable(cls) else "?"
            print(f"  [OK]  {cls_name:35s} in {mod_path}")
        except Exception as exc:
            print(f"  [FAIL] {cls_name:35s} in {mod_path}  ERROR: {exc}")
            failed.append((cls_name, mod_path, str(exc)))

    print()
    if failed:
        for label, path, err in failed:
            print(f"PHASE FAILED: PHASE 0 — SYSTEM DISCOVERY")
            print(f"REASON: {err}")
            print(f"MISSING: {label}")
            print(f"BLOCKING PATH: {path}")
        sys.exit(1)

    print("PHASE 0 RESULT: ALL ENTRY POINTS VERIFIED")

if __name__ == "__main__":
    run()
