"""Standalone test to verify replay engine decomposition."""
import sys
import importlib

errors = []

# 1. Verify all imports work
print("=== Import Verification ===")
modules = [
    "analytics.replay.fill_recorder",
    "analytics.replay.signal_processor",
    "analytics.replay.position_closer",
    "analytics.replay.engine",
    "analytics.replay",
]
for mod_name in modules:
    try:
        mod = importlib.import_module(mod_name)
        print(f"  OK: {mod_name}")
    except Exception as e:
        print(f"  FAIL: {mod_name}: {e}")
        errors.append(mod_name)

# 2. Verify ReplayEngine backward-compatible attributes
print("\n=== Backward Compatibility ===")
from analytics.replay.engine import ReplayEngine

engine_methods = [
    "run", "compute_statistics",
    "_process_signal", "_process_signal_simulated", "_process_signal_via_oms",
    "_close_position", "_close_position_at_price",
    "_record_session_fill", "_compute_commission", "_compute_slippage_pct",
    "_sync_session_from_tracker",
    "_run_features", "_run_single", "_run_multi_symbol",
    "_new_window_state", "_append_bar_window", "_window_dataframe", "_build_window",
    "_publish_scheduled_events", "_publish_signal",
]
for method_name in engine_methods:
    if hasattr(ReplayEngine, method_name):
        print(f"  OK: {method_name}")
    else:
        print(f"  MISSING: {method_name}")
        errors.append(method_name)

# 3. Verify new classes exist with expected interfaces
print("\n=== New Module Interfaces ===")
from analytics.replay.fill_recorder import FillRecorder
from analytics.replay.signal_processor import SignalProcessor
from analytics.replay.position_closer import PositionCloser

for cls_name, methods in [
    ("FillRecorder", ["record", "compute_commission", "compute_slippage_pct"]),
    ("SignalProcessor", ["process"]),
    ("PositionCloser", ["close", "close_at_price", "sync_from_tracker"]),
]:
    cls = {"FillRecorder": FillRecorder, "SignalProcessor": SignalProcessor, "PositionCloser": PositionCloser}[cls_name]
    for m in methods:
        if hasattr(cls, m):
            print(f"  OK: {cls_name}.{m}")
        else:
            print(f"  MISSING: {cls_name}.{m}")
            errors.append(f"{cls_name}.{m}")

# 4. Verify no circular imports
print("\n=== Dependency Direction ===")
import ast

for module_path, module_name in [
    ("src/analytics/replay/fill_recorder.py", "fill_recorder"),
    ("src/analytics/replay/signal_processor.py", "signal_processor"),
    ("src/analytics/replay/position_closer.py", "position_closer"),
]:
    with open(module_path) as f:
        tree = ast.parse(f.read())
    bad = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module and "engine" in node.module:
            bad.append(node)
    if bad:
        print(f"  CIRCULAR: {module_name} imports from engine!")
        errors.append(f"circular:{module_name}")
    else:
        print(f"  OK: {module_name} does NOT import from engine")

# 5. Verify engine delegates properly
print("\n=== Delegation Wiring ===")
engine = ReplayEngine(allow_simulate_without_oms=True)
has_recorder = hasattr(engine, "_fill_recorder") and isinstance(engine._fill_recorder, FillRecorder)
has_processor = hasattr(engine, "_signal_processor") and isinstance(engine._signal_processor, SignalProcessor)
has_closer = hasattr(engine, "_position_closer") and isinstance(engine._position_closer, PositionCloser)
print(f"  FillRecorder wired: {has_recorder}")
print(f"  SignalProcessor wired: {has_processor}")
print(f"  PositionCloser wired: {has_closer}")
if not all([has_recorder, has_processor, has_closer]):
    errors.append("delegation-wiring")

# Summary
print(f"\n{'='*40}")
if errors:
    print(f"FAILED: {len(errors)} error(s)")
    for e in errors:
        print(f"  - {e}")
    sys.exit(1)
else:
    print("ALL CHECKS PASSED")
