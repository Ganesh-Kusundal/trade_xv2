"""Generate golden-file binary packets for Dhan depth-20 and depth-200 feeds.

The fixtures produced here are written to disk so the regression suite parses
real bytes (capturing the exact header layout Dhan documents for each depth
endpoint) instead of relying on in-test synthesized packets.

Run from repo root:

    python scripts/generate_depth_golden_packets.py

Output:
    brokers/dhan/tests/fixtures/depth_20_packet.bin
    brokers/dhan/tests/fixtures/depth_200_packet.bin

Why this exists
---------------
Plan §5.1 surfaced that the previous harness packet used the *same* layout
for both depth-20 and depth-200 tests, hiding a header-layout mismatch
(depth-20: ``security_id`` at offset 4; depth-200: ``num_rows`` at offset 8).
The golden files below encode each layout exactly once, so a regression that
flips the offset is caught immediately.

NOTE: these are *structurally correct* packets built from public layout docs.
If a real Dhan session is later captured into ``*.bin`` files, drop the
recorded bytes over these defaults — they will be parsed the same way because
the layout constants below match what production parsers read.
"""

from __future__ import annotations

import struct
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
FIXTURE_DIR = REPO_ROOT / "brokers" / "dhan" / "tests" / "fixtures"

# Response codes (must match brokers.dhan.depth_20/200 constants)
DEPTH_20_BID = 41
DEPTH_20_ASK = 51
DEPTH_200_BID = 41
DEPTH_200_ASK = 51

# Header / level sizes (must match brokers.dhan.depth_20/200 constants)
HEADER_SIZE = 12
LEVEL_SIZE = 16


def build_depth20_packet(response_code: int, security_id: int, levels: list[tuple[float, int, int]]) -> bytes:
    """Build a depth-20 packet per documented layout.

    Layout:
        [0:2]  length (uint16 LE)
        [2]    response_code (uint8)
        [3]    message_version (uint8)
        [4:8]  security_id    (uint32 LE)
        [8:12] reserved
        [12:]  N x 16-byte levels (price<d>, qty<I>, orders<I>)
    """
    total_slots = 20
    body_size = total_slots * LEVEL_SIZE
    packet = bytearray(HEADER_SIZE + body_size)
    struct.pack_into("<H", packet, 0, HEADER_SIZE + body_size)
    packet[2] = response_code
    packet[3] = 1
    struct.pack_into("<I", packet, 4, security_id)
    for i, (price, qty, orders) in enumerate(levels[:total_slots]):
        offset = HEADER_SIZE + i * LEVEL_SIZE
        struct.pack_into("<d", packet, offset, price)
        struct.pack_into("<I", packet, offset + 8, qty)
        struct.pack_into("<I", packet, offset + 12, orders)
    return bytes(packet)


def build_depth200_packet(response_code: int, num_rows: int, levels: list[tuple[float, int, int]]) -> bytes:
    """Build a depth-200 packet per documented layout.

    Layout:
        [0:2]  length (uint16 LE)
        [2]    response_code (uint8)
        [3]    message_version (uint8)
        [4:8]  reserved
        [8:12] num_rows       (uint32 LE)
        [12:]  num_rows x 16-byte levels (price<d>, qty<I>, orders<I>)
    """
    body_size = num_rows * LEVEL_SIZE
    packet = bytearray(HEADER_SIZE + body_size)
    struct.pack_into("<H", packet, 0, HEADER_SIZE + body_size)
    packet[2] = response_code
    packet[3] = 1
    struct.pack_into("<I", packet, 8, num_rows)
    for i, (price, qty, orders) in enumerate(levels[:num_rows]):
        offset = HEADER_SIZE + i * LEVEL_SIZE
        struct.pack_into("<d", packet, offset, price)
        struct.pack_into("<I", packet, offset + 8, qty)
        struct.pack_into("<I", packet, offset + 12, orders)
    return bytes(packet)


def main() -> None:
    FIXTURE_DIR.mkdir(parents=True, exist_ok=True)

    # ── depth-20 ─────────────────────────────────────────────────────────────
    # Security ID = 2885 (RELIANCE on NSE_EQ). Five real bid levels.
    depth20_bids = [
        (2450.55, 100, 5),
        (2450.45, 250, 8),
        (2450.30, 75, 3),
        (2450.10, 500, 12),
        (2449.95, 1000, 25),
    ]
    depth20_asks = [
        (2450.65, 80, 4),
        (2450.75, 320, 10),
        (2450.90, 60, 2),
        (2451.10, 410, 9),
        (2451.25, 880, 18),
    ]
    (FIXTURE_DIR / "depth_20_packet.bin").write_bytes(
        build_depth20_packet(DEPTH_20_BID, 2885, depth20_bids)
    )
    (FIXTURE_DIR / "depth_20_ask_packet.bin").write_bytes(
        build_depth20_packet(DEPTH_20_ASK, 2885, depth20_asks)
    )

    # ── depth-200 ────────────────────────────────────────────────────────────
    # 25 levels on each side. Security id is implicit (depth-200 = 1 per conn).
    depth200_bids = [
        (2450.55 - i * 0.05, (100 + i * 25) % 5000, (5 + i) % 50)
        for i in range(25)
    ]
    depth200_asks = [
        (2450.65 + i * 0.05, (80 + i * 30) % 5000, (4 + i) % 50)
        for i in range(25)
    ]
    (FIXTURE_DIR / "depth_200_packet.bin").write_bytes(
        build_depth200_packet(DEPTH_200_BID, 25, depth200_bids)
    )
    (FIXTURE_DIR / "depth_200_ask_packet.bin").write_bytes(
        build_depth200_packet(DEPTH_200_ASK, 25, depth200_asks)
    )

    print(f"Wrote depth-20 packets (security_id=2885) to {FIXTURE_DIR}")
    print(f"Wrote depth-200 packets (25 levels) to {FIXTURE_DIR}")


if __name__ == "__main__":
    main()