"""
Base MCP Class
--------------

All Model Context Protocol (MCP) implementations inherit from
``MCPBase``.  It provides common functionality such as retry logic,
self‑healing hooks, logging, and integration with the Allure reporter.

Concrete subclasses implement the `_execute_step` method to perform
domain‑specific actions (UI, API, Mobile, SQL).  Each step is a
dictionary describing the action and any inputs.
"""

import time
from typing import Any, Dict, List

from ..utils.logger import get_logger


class MCPBase:
    """Base class for all MCPs providing retry and logging behaviour."""

    def __init__(self, config, reporter) -> None:
        self.config = config
        self.reporter = reporter
        self.logger = get_logger(self.__class__.__name__)
        self.max_retries = int(config.get("mcp.max_retries", 3))
        self.retry_interval = int(config.get("mcp.retry_interval_seconds", 2))

    def run(self, steps: List[Dict[str, Any]]) -> None:
        """Execute a sequence of steps with retry and self‑healing.

        Each step is executed via `_execute_step`.  If execution fails,
        an attempt is made to recover using `_self_heal`.  Steps are
        retried up to `max_retries` times.  On exhaustion of retries
        the exception is re‑raised so that upstream callers may handle
        the error (e.g. log alerts or abort the test run).
        """
        for idx, step in enumerate(steps):
            attempt = 0
            while True:
                try:
                    self.logger.debug("Executing step %s: %s", idx + 1, step)
                    self._execute_step(step)
                    break
                except Exception as exc:
                    attempt += 1
                    self.logger.warning(
                        "Step %s failed on attempt %s/%s: %s",
                        idx + 1,
                        attempt,
                        self.max_retries,
                        exc,
                    )
                    self.reporter.attach_text(
                        f"Step {idx + 1} failure on attempt {attempt}: {exc}",
                        name=f"error_step_{idx + 1}_attempt_{attempt}",
                    )
                    # Attempt self healing
                    try:
                        healed = self._self_heal(step, exc)
                        if healed:
                            self.logger.info("Self‑healing succeeded for step %s on attempt %s", idx + 1, attempt)
                            continue
                    except Exception as heal_exc:
                        self.logger.error("Self‑healing failed: %s", heal_exc)
                    if attempt >= self.max_retries:
                        self.logger.error("Step %s failed after %s attempts", idx + 1, attempt)
                        raise
                    time.sleep(self.retry_interval)

    def _execute_step(self, step: Dict[str, Any]) -> None:
        """Execute a single step.  Must be implemented by subclasses."""
        raise NotImplementedError

    def _self_heal(self, step: Dict[str, Any], exc: Exception) -> bool:
        """Attempt to recover from a step failure.

        Subclasses may override this method to implement selector
        recovery, AI‑based element matching or other heuristics.  The
        default implementation performs no recovery and returns False.
        If a subclass returns True the framework will retry the step
        immediately without incrementing the attempt counter.
        """
        return False