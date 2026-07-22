"""Walk-forward window splitter."""

from __future__ import annotations


def split_windows(
    n: int,
    train: int,
    test: int,
    step: int | None = None,
) -> list[tuple[int, int, int, int]]:
    """
    Yield (train_start, train_end, test_start, test_end) half-open indices.
    Default step = test (non-overlapping test, rolling train).
    """
    if train <= 0 or test <= 0 or n < train + test:
        return []
    stride = step if step is not None else test
    out: list[tuple[int, int, int, int]] = []
    start = 0
    while start + train + test <= n:
        ts, te = start, start + train
        out.append((ts, te, te, te + test))
        start += stride
    return out
