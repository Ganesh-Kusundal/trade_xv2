"""Minimal diagnostic: just create broker and check resolver state."""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
print("START")
from brokers.dhan.broker import DhanBroker

print("IMPORT OK")
broker = DhanBroker.from_env(env_path=PROJECT_ROOT / ".env.local")
print(f"BROKER OK type={type(broker).__name__}")
r = broker.instrument_resolver
print(f"LOADED={r.is_loaded}")
print(f"SIZE={r.size}")
print(f"BY_ID={len(r._by_security_id)}")
print(f"BY_SYM={len(r._by_symbol)}")
# Search reliance without loading
matches = [
    d
    for d in r._by_security_id.values()
    if "reliance" in d.symbol.lower() or "reliance" in d.canonical_symbol.lower()
]
print(f"RELIANCE_MATCHES={len(matches)}")
for m in matches[:10]:
    print(f"  {m.security_id} {m.symbol} {m.canonical_symbol} {m.exchange_segment}")
print("END")
