import sys
import traceback
from pathlib import Path

lines = []
try:
    from brokers.dhan.broker import DhanBroker

    b = DhanBroker.from_env(env_path=Path(".env.local"))
    lines.append(f"SUCCESS: {type(b).__name__}")
    lines.append(f"client_id: {getattr(b, 'client_id', 'N/A')}")
    # Try live calls
    try:
        f = b.get_fund_limits()
        lines.append(f"fund_limits: {f}")
    except Exception:
        lines.append("get_fund_limits FAILED:\n" + traceback.format_exc())
    try:
        p = b.get_positions()
        lines.append(f"positions: {len(p)} items")
    except Exception:
        lines.append("get_positions FAILED:\n" + traceback.format_exc())
    try:
        h = b.get_holdings()
        lines.append(f"holdings: {len(h)} items")
    except Exception:
        lines.append("get_holdings FAILED:\n" + traceback.format_exc())
except Exception:
    lines.append("FAILED")
    lines.append(traceback.format_exc())

Path("debug_output.txt").write_text("\n".join(lines))
print("WROTE debug_output.txt")
