"""Shared parallel batch execution for broker and datalake gateways."""

from __future__ import annotations

import logging
from collections.abc import Callable, Iterator
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from typing import TypeVar

from domain.constants import BATCH_MAX_WORKERS

logger = logging.getLogger(__name__)

T = TypeVar("T")


def batch_execute(
    items: list[str],
    fn: Callable[[str], T],
    *,
    max_workers: int = BATCH_MAX_WORKERS,
    on_error: Callable[[str, Exception], None] | None = None,
) -> dict[str, T]:
    """Execute *fn* for each item in parallel; omit failed items from results."""
    if not items:
        return {}

    results: dict[str, T] = {}
    pending: dict = {}
    item_iter: Iterator[str] = iter(items)

    def _submit_next(executor: ThreadPoolExecutor) -> None:
        try:
            item = next(item_iter)
        except StopIteration:
            return
        pending[executor.submit(fn, item)] = item

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        for _ in range(min(max_workers, len(items))):
            _submit_next(executor)
        while pending:
            done, _ = wait(pending, return_when=FIRST_COMPLETED)
            for future in done:
                item = pending.pop(future)
                try:
                    results[item] = future.result()
                except Exception as exc:
                    if on_error is not None:
                        on_error(item, exc)
                    else:
                        logger.debug("batch_execute failed for %s: %s", item, exc)
                _submit_next(executor)
    return results
