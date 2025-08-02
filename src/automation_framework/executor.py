"""
Concurrent Test Executor
-----------------------

This module defines a simple thread‑pool based executor for running
test cases in parallel.  It abstracts the details of creating the
pool and waiting for results.  The router uses this executor when
concurrency is enabled in the configuration.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from typing import Callable, Iterable, Optional

from .utils.logger import get_logger


class TestExecutor:
    """Manage a thread pool for parallel test execution."""

    def __init__(self, max_workers: int = 4) -> None:
        self.max_workers = max_workers
        self.logger = get_logger(self.__class__.__name__)
        self._executor: Optional[ThreadPoolExecutor] = None

    def __enter__(self) -> "TestExecutor":
        self._executor = ThreadPoolExecutor(max_workers=self.max_workers)
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        if self._executor:
            self._executor.shutdown(wait=True)
            self._executor = None

    def submit(self, fn: Callable, *args, **kwargs):
        if not self._executor:
            # lazily create executor
            self._executor = ThreadPoolExecutor(max_workers=self.max_workers)
        return self._executor.submit(fn, *args, **kwargs)

    def map(self, func: Callable, iterable: Iterable) -> list:
        if not self._executor:
            self._executor = ThreadPoolExecutor(max_workers=self.max_workers)
        futures = [self._executor.submit(func, item) for item in iterable]
        results = []
        for f in futures:
            try:
                results.append(f.result())
            except Exception as exc:
                self.logger.error("Task execution failed: %s", exc)
                results.append(None)
        return results

    def shutdown(self) -> None:
        if self._executor:
            self._executor.shutdown(wait=True)
            self._executor = None


__all__ = ["TestExecutor"]