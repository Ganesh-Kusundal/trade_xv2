"""Script to remove Phase/Task/REF markers from infrastructure files."""
import re

def clean_file(path, replacements):
    with open(path, 'r') as f:
        content = f.read()
    for old, new in replacements:
        if old not in content:
            print(f"  WARNING: not found in {path}: {old!r}")
        content = content.replace(old, new)
    with open(path, 'w') as f:
        f.write(content)
    print(f"  Cleaned: {path}")

# ── File 1: event_bus/event_bus.py ──────────────────────────────────────
print("File 1: event_bus.py")
clean_file("infrastructure/event_bus/event_bus.py", [
    # Line 50: docstring marker
    ("    P4-Phase 4: Added replay_mode for deterministic replay.\n",
     "    Added replay_mode for deterministic replay.\n"),
    # Line 94: parameter doc
    ("        P4: If True, disables auto-persistence and preserves original\n",
     "        If True, disables auto-persistence and preserves original\n"),
    # Line 111: inline comment (whole line marker)
    ("        replay_mode: bool = False,  # P4\n",
     "        replay_mode: bool = False,\n"),
    # Line 114: inline comment with meaningful text after marker
    ("        max_processed_events: int = 10000,  # P5: Idempotency cache size\n",
     "        max_processed_events: int = 10000,  # Idempotency cache size\n"),
    # Lines 116-118: Task 4.4 prefix in comment block
    ("        # Task 4.4: Lock sharding — separate lightweight Lock for subscriber\n",
     "        # Lock sharding — separate lightweight Lock for subscriber\n"),
    # Line 127: inline marker
    ("        self._replay_mode = replay_mode  # P4\n",
     "        self._replay_mode = replay_mode\n"),
    # Line 128: (Task 4.4) suffix
    ("        # self._sequence_counter replaced by lock-free self._sequence (Task 4.4)\n",
     "        # self._sequence_counter replaced by lock-free self._sequence\n"),
    # Line 134: P5 prefix
    ("        # P5: Idempotency - track processed event_ids to prevent duplicate processing\n",
     "        # Idempotency - track processed event_ids to prevent duplicate processing\n"),
    # Line 145: (P4) in docstring
    ('        """True if bus is in replay mode (P4)."""',
     '        """True if bus is in replay mode."""'),
    # Line 149: (P4) in docstring
    ('        """Enable or disable replay mode (P4).\n',
     '        """Enable or disable replay mode.\n'),
    # Line 281: P4 prefix in comment
    ("        # P4: Assign sequence number in live mode only\n",
     "        # Assign sequence number in live mode only\n"),
    # Line 282: Task 4.4 prefix
    ("        # Task 4.4: Lock-free — ``next(itertools.count(1))`` is atomic under\n",
     "        # Lock-free — ``next(itertools.count(1))`` is atomic under\n"),
    # Lines 301-302: P5 prefix in docstring
    ("        P5: Under at-least-once delivery (websockets, network retries),\n",
     "        Under at-least-once delivery (websockets, network retries),\n"),
    # Lines 338-339: P4-Phase 4 prefix in docstring
    ("        P4-Phase 4: In replay_mode, auto-persistence is disabled and\n",
     "        In replay_mode, auto-persistence is disabled and\n"),
    # Lines 344-345: P5 prefix in docstring
    ("        P5: Idempotency - duplicate events (same event_id) are silently\n",
     "        Idempotency - duplicate events (same event_id) are silently\n"),
    # Line 357: P4 prefix in comment
    ("            # P4: Skip persistence in replay mode (no recursive writes)\n",
     "            # Skip persistence in replay mode (no recursive writes)\n"),
])

# ── File 2: event_log.py ────────────────────────────────────────────────
print("File 2: event_log.py")
clean_file("infrastructure/event_log.py", [
    # Line 285: section header marker
    ("# BufferedEventLog (P3-Phase 3)\n",
     "# BufferedEventLog\n"),
    # Line 359: inline marker
    ('                "correlation_id": event.correlation_id,  # B5\n',
     '                "correlation_id": event.correlation_id,\n'),
    # Line 360: inline marker
    ('                "sequence_number": event.sequence_number,  # B5\n',
     '                "sequence_number": event.sequence_number,\n'),
])

# ── File 3: logging_config.py ───────────────────────────────────────────
print("File 3: logging_config.py")
clean_file("infrastructure/logging_config.py", [
    # Line 7: (REF-29) in section heading
    ("Token-leak protection (REF-29)\n",
     "Token-leak protection\n"),
    # Line 35: (REF-29) inline comment
    ("# Token redaction patterns (REF-29)\n",
     "# Token redaction patterns\n"),
])

# ── File 4: observability/http_server.py ────────────────────────────────
print("File 4: http_server.py")
clean_file("infrastructure/observability/http_server.py", [
    # Line 3: "Phase B / B8 + B9: " prefix
    ("Phase B / B8 + B9: the system previously had no way for an operator\n",
     "The system previously had no way for an operator\n"),
    # Line 19: "Excluded from B8/B9:" 
    ("Excluded from B8/B9:\n",
     "Excluded from the initial observability surface:\n"),
])

# ── File 5: observability/tracing.py ────────────────────────────────────
print("File 5: tracing.py")
clean_file("infrastructure/observability/tracing.py", [
    # Line 3: "P5 Stability Engineering: " prefix
    ("P5 Stability Engineering: Automatic tracing for order lifecycle, trade execution,\n",
     "Automatic tracing for order lifecycle, trade execution,\n"),
])

print("\nDone. All markers removed.")
