"""
Web Driver
----------

This module defines :class:`WebDriver`, a thin wrapper over
Playwright for executing web UI test cases.  The driver handles
navigation, clicking, filling fields and simple text assertions.  It
integrates with the locator repository to persist selectors and uses
the LLM agent for self‑healing when a selector fails.  Results are
recorded in the database at both the run and step level.

If Playwright is not installed the driver falls back to dummy
implementations so that the rest of the framework can be exercised
without browser automation capabilities.  Dummy mode logs actions
but does not interact with a real browser.
"""

from __future__ import annotations

import logging
import json
import time
from typing import Any, Dict, List, Optional

try:
    from playwright.sync_api import sync_playwright, TimeoutError as PWTimeoutError
    _playwright_available = True
except Exception:
    _playwright_available = False

from ..utils import wait_utils
from ..utils.locator_repository import LocatorRepository
from ..utils.db_utils import Database
from ..llm_integration.llm_agent import LLMAgent


class _DummyPage:
    """Fallback dummy page used when Playwright is unavailable."""
    def goto(self, url: str) -> None:
        logging.getLogger(__name__).info("[Dummy] goto %s", url)
    def click(self, selector: str) -> None:
        logging.getLogger(__name__).info("[Dummy] click %s", selector)
    def fill(self, selector: str, value: str) -> None:
        logging.getLogger(__name__).info("[Dummy] fill %s with %s", selector, value)
    def locator(self, selector: str) -> "_DummyPage":
        return self
    def inner_text(self) -> str:
        return ""
    def screenshot(self, path: str) -> None:
        with open(path, "wb") as f:
            f.write(b"")
    def wait_for_selector(self, *args, **kwargs) -> None:
        pass
    def wait_for_load_state(self, *args, **kwargs) -> None:
        pass


class _DummyContext:
    def new_page(self) -> _DummyPage:
        return _DummyPage()
    def close(self) -> None:
        pass


class _DummyBrowser:
    def new_context(self) -> _DummyContext:
        return _DummyContext()
    def close(self) -> None:
        pass


class WebDriver:
    """Execute web UI test cases using Playwright with self‑healing support."""

    def __init__(self, config: Any, db: Database) -> None:
        self.config = config
        self.db = db
        self.llm = LLMAgent(config)
        self.loc_repo = LocatorRepository(config)
        self.browser_type = None
        try:
            self.browser_type = config.get("ui", {}).get("browser", "chromium")  # type: ignore
        except Exception:
            self.browser_type = "chromium"
        try:
            self.headless = bool(config.get("ui", {}).get("headless", True))  # type: ignore
        except Exception:
            self.headless = True
        self._playwright = None
        self._browser = None
        self._context = None
        self._page = None

    def _ensure_page(self) -> None:
        """Lazy creation of Playwright browser and page objects."""
        if self._page is not None:
            return
        if _playwright_available:
            self._playwright = sync_playwright().start()
            browser_fn = getattr(self._playwright, self.browser_type)
            self._browser = browser_fn.launch(headless=self.headless)
            self._context = self._browser.new_context()
            self._page = self._context.new_page()
        else:
            # Fallback to dummy implementations
            self._playwright = None
            self._browser = _DummyBrowser()
            self._context = _DummyContext()
            self._page = _DummyPage()

    def close(self) -> None:
        """Close the browser context and Playwright instance."""
        if self._page is None:
            return
        try:
            if self._context:
                self._context.close()
        except Exception:
            pass
        try:
            if self._browser:
                self._browser.close()
        except Exception:
            pass
        try:
            if self._playwright:
                self._playwright.stop()
        except Exception:
            pass
        self._playwright = None
        self._browser = None
        self._context = None
        self._page = None

    def run_test_case(self, case: Dict[str, Any]) -> int:
        """Execute a single test case and record results in the database.

        This implementation continues executing all steps even when some
        fail.  Individual step results are recorded as ``passed``,
        ``failed`` or ``skipped`` (for steps with missing data).  The
        overall status for the run is derived from the aggregate of
        step results: ``passed`` if all steps pass, ``failed`` if all
        executed steps fail, and ``partial`` when there is a mix of
        outcomes.  An empty test will be marked as ``skipped``.

        :param case: A dictionary containing keys ``user_story``, ``test_set`` and ``steps``.
        :returns: The ID of the test run record.
        """
        self._ensure_page()
        # Insert test case into the database if not already present
        test_case_id = case.get("id")
        if not test_case_id:
            test_case_id = self.db.add_test_case(case)
        # Record the run start
        start_time = time.time()
        run_id = self.db.add_test_run(
            test_case_id,
            status="running",
            started_at=_iso(start_time),
            ended_at=_iso(start_time),
        )
        # Counters for deriving final status
        passed_steps = 0
        failed_steps = 0
        skipped_steps = 0
        error_message: Optional[str] = None
        steps = case.get("steps", []) or []
        for idx, step in enumerate(steps):
            step_start = time.time()
            status = "passed"
            message: Optional[str] = None
            try:
                # Honour dependent steps: if a step depends on a previous step
                # index and that step failed or was skipped, skip this one.
                dep = step.get("depends_on")
                if dep is not None and isinstance(dep, int):
                    # Determine status of dependency
                    # We fetch previously recorded run_steps from the DB for this run
                    prev_results = self.db.get_run_steps(run_id) if run_id else []
                    # Find the run result for the dependency
                    for r in prev_results:
                        if r.get("step_index") == dep and r.get("status") in {"failed", "skipped"}:
                            raise ValueError(f"Step depends_on {dep} which did not pass")
                self._execute_step(step)
            except ValueError as ve:
                # Missing required information results in a skipped step
                status = "skipped"
                message = str(ve)
                skipped_steps += 1
            except Exception as exc:
                # Record failure but continue executing subsequent steps
                status = "failed"
                message = str(exc)
                failed_steps += 1
                error_message = message
            else:
                passed_steps += 1
            step_end = time.time()
            self.db.add_run_step(run_id, idx, status, message, _iso(step_start), _iso(step_end))
        # Determine overall status
        end_time = time.time()
        executed = passed_steps + failed_steps
        if executed == 0 and skipped_steps > 0:
            overall_status = "skipped"
        elif failed_steps == 0 and skipped_steps == 0:
            overall_status = "passed"
        elif failed_steps == executed:
            overall_status = "failed"
        else:
            overall_status = "partial"
        # Persist run metadata
        self.db.conn.cursor().execute(
            """
            UPDATE test_runs
            SET status = ?, ended_at = ?, error_message = ?
            WHERE id = ?
            """,
            (overall_status, _iso(end_time), error_message, run_id),
        )
        self.db.conn.commit()
        # Close the browser context after running the test
        self.close()
        return run_id

    def _execute_step(self, step: Dict[str, Any]) -> None:
        """Execute an individual step on the page.

        Supported actions include ``goto``, ``click``, ``fill`` and ``assert_text``.  If a
        selector is not provided the locator repository is queried and
        heuristics or the LLM agent may be consulted to derive one.
        """
        action = step.get("action")
        if not action:
            raise ValueError("Step missing 'action'")
        page = self._page
        if not page:
            raise RuntimeError("Page not initialised")
        # Navigation
        if action == "goto":
            url = step.get("url") or step.get("target")
            if not url:
                raise ValueError("'goto' action requires a 'url' or 'target'")
            page.goto(url)
            # Wait for the page and any embedded WebViews to stabilise
            try:
                from ..utils.webview_utils import stabilise_webview  # import lazily
                stabilise_webview(page, self.config)
            except Exception:
                wait_utils.wait_for_page_stable(page, self.config)
            return
        # Prepare selector
        selector: Optional[str] = step.get("selector")
        step_key = LocatorRepository.compute_step_key(step)
        stored = self.loc_repo.get_locator("ui", step_key)
        if stored:
            if stored["type"].lower() in ("css", "selector", "aria", "role"):
                selector = stored["value"]
            elif stored["type"].lower() == "xpath":
                selector = f"xpath={stored['value']}"
            elif stored["type"].lower() == "text":
                selector = f"text={stored['value']}"
            else:
                selector = stored["value"]
        if not selector:
            # Fallback heuristics: derive from target/element/text
            for key in ("selector", "target", "element", "text", "label", "value"):
                if key in step and step[key]:
                    selector = f"text={step[key]}"
                    break
            # Ask LLM for a suggestion if heuristics fail
            if not selector:
                try:
                    description = json.dumps(step, ensure_ascii=False)  # type: ignore[name-defined]
                except Exception:
                    description = str(step)
                suggestion = self.llm.suggest_ui_locator(description)
                if suggestion:
                    selector = suggestion
                    # Persist the suggested locator
                    self.loc_repo.add_locator("ui", step_key, {"type": "css", "value": selector})
        # Wait for element if necessary.  Before waiting, check if the
        # selector may match multiple elements.  When using Playwright
        # this can be determined via the ``count`` method on the locator.
        if action in ("click", "fill", "assert_text") and selector:
            try:
                if _playwright_available and hasattr(page, "locator"):
                    count = page.locator(selector).count()
                    if count > 1:
                        logging.getLogger(__name__).warning(
                            "Multiple elements (%s) matched selector '%s'; using the first", count, selector
                        )
            except Exception:
                pass
            wait_utils.wait_for_element_ui(page, selector, self.config)
        # Execute the action
        if action == "click":
            page.click(selector)
        elif action == "fill":
            value = step.get("value") or step.get("input_data") or ""
            page.fill(selector, str(value))
        elif action == "assert_text":
            expected = step.get("expected") or step.get("value") or ""
            actual = page.locator(selector).inner_text().strip()
            if actual != str(expected).strip():
                raise AssertionError(f"Expected text '{expected}' but found '{actual}'")
        else:
            raise ValueError(f"Unsupported action: {action}")
        # Wait for page stability after each action
        wait_utils.wait_for_page_stable(page, self.config)


def _iso(ts: float) -> str:
    """Convert a timestamp in seconds since the epoch to ISO format."""
    return time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(ts))


__all__ = ["WebDriver"]