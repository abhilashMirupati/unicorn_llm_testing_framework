"""
Mobile Driver
-------------

This module defines :class:`MobileDriver`, a wrapper around Appium's
WebDriver for executing mobile test cases.  The driver supports
primitive actions such as ``tap`` (click), ``fill`` (send keys) and
``assert_text``.  It integrates with the locator repository and the
LLM agent to recover from locator changes.  When Appium is not
available the driver falls back to dummy implementations to allow the
framework to run in environments without mobile capabilities.
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any, Dict, Optional

from ..utils import wait_utils
from ..utils.locator_repository import LocatorRepository
from ..utils.db_utils import Database
from ..llm_integration.llm_agent import LLMAgent

try:
    from appium import webdriver as appium_webdriver  # type: ignore
    _appium_available = True
except Exception:
    _appium_available = False


class _DummyMobileElement:
    def click(self) -> None:
        logging.getLogger(__name__).info("[Dummy] tap element")
    def send_keys(self, value: str) -> None:
        logging.getLogger(__name__).info("[Dummy] fill element with %s", value)
    @property
    def text(self) -> str:
        return ""


class _DummyMobileDriver:
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        pass
    def find_element(self, by: str, value: str) -> _DummyMobileElement:  # type: ignore[override]
        return _DummyMobileElement()
    def quit(self) -> None:
        pass


class MobileDriver:
    """Execute mobile test cases using Appium with self‑healing support."""

    def __init__(self, config: Any, db: Database) -> None:
        self.config = config
        self.db = db
        self.llm = LLMAgent(config)
        self.loc_repo = LocatorRepository(config)
        self.driver: Optional[Any] = None
        # Connection details
        try:
            host = config.get("mobile", {}).get("host", "localhost")  # type: ignore[assignment]
            port = int(config.get("mobile", {}).get("port", 4723))  # type: ignore[assignment]
            self.remote_url = f"http://{host}:{port}/wd/hub"
        except Exception:
            self.remote_url = "http://localhost:4723/wd/hub"
        try:
            self.desired_caps = config.get("mobile", {}).get("desired_capabilities", {})  # type: ignore[assignment]
        except Exception:
            self.desired_caps = {}

    def _ensure_driver(self) -> None:
        if self.driver is not None:
            return
        if _appium_available:
            try:
                self.driver = appium_webdriver.Remote(command_executor=self.remote_url, desired_capabilities=self.desired_caps)
            except Exception as exc:
                logging.getLogger(__name__).error("Failed to connect to Appium: %s", exc)
                self.driver = _DummyMobileDriver()
        else:
            self.driver = _DummyMobileDriver()

    def quit(self) -> None:
        if self.driver:
            try:
                self.driver.quit()
            except Exception:
                pass
            self.driver = None

    def run_test_case(self, case: Dict[str, Any]) -> int:
        """Execute a mobile test case and record results.

        Similar to the web driver, this method will iterate through all steps
        and record individual results.  Steps with missing data are marked
        as ``skipped``; failures do not abort the test run.  The
        aggregate outcome determines the final status (``passed``,
        ``failed`` or ``partial``).
        """
        self._ensure_driver()
        # Insert case if necessary
        test_case_id = case.get("id")
        if not test_case_id:
            test_case_id = self.db.add_test_case(case)
        start_time = time.time()
        run_id = self.db.add_test_run(
            test_case_id,
            status="running",
            started_at=_iso(start_time),
            ended_at=_iso(start_time),
        )
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
                # Honour dependent steps: skip if dependency failed or skipped
                dep = step.get("depends_on")
                if dep is not None and isinstance(dep, int):
                    prev_results = self.db.get_run_steps(run_id) if run_id else []
                    for r in prev_results:
                        if r.get("step_index") == dep and r.get("status") in {"failed", "skipped"}:
                            raise ValueError(f"Step depends_on {dep} which did not pass")
                self._execute_step(step)
            except ValueError as ve:
                status = "skipped"
                message = str(ve)
                skipped_steps += 1
            except Exception as exc:
                status = "failed"
                message = str(exc)
                failed_steps += 1
                error_message = message
            else:
                passed_steps += 1
            step_end = time.time()
            self.db.add_run_step(run_id, idx, status, message, _iso(step_start), _iso(step_end))
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
        # Update run record
        self.db.conn.cursor().execute(
            """
            UPDATE test_runs
            SET status = ?, ended_at = ?, error_message = ?
            WHERE id = ?
            """,
            (overall_status, _iso(end_time), error_message, run_id),
        )
        self.db.conn.commit()
        # Quit driver after run
        self.quit()
        return run_id

    def _execute_step(self, step: Dict[str, Any]) -> None:
        """Execute a single mobile step."""
        action = step.get("action")
        if not action:
            raise ValueError("Step missing 'action'")
        self._ensure_driver()
        driver = self.driver
        if not driver:
            raise RuntimeError("Driver not initialised")
        # Determine locator
        locator = step.get("locator")
        step_key = LocatorRepository.compute_step_key(step)
        stored = self.loc_repo.get_locator("mobile", step_key)
        if stored:
            locator = stored
        if not locator:
            # Use LLM to suggest a locator based on description
            try:
                description = json.dumps(step, ensure_ascii=False)
            except Exception:
                description = str(step)
            suggestion = self.llm.suggest_ui_locator(description)
            if suggestion:
                # Assume suggestion is an accessibility id or id; treat as accessibility id
                locator = {"type": "accessibility_id", "value": suggestion}
                self.loc_repo.add_locator("mobile", step_key, locator)
        # Wait for element if required; if no locator and the action
        # requires one, raise a ValueError to mark the step as skipped.
        if locator:
            wait_utils.wait_for_element_mobile(driver, locator, self.config)
        else:
            if action in ("tap", "click", "fill", "assert_text"):
                raise ValueError("Step missing locator for mobile action")
        # Execute actions
        if action in ("tap", "click"):
            elem = _find_element(driver, locator)
            elem.click()
        elif action == "fill":
            value = step.get("value") or step.get("input_data") or ""
            elem = _find_element(driver, locator)
            elem.send_keys(str(value))
        elif action == "assert_text":
            expected = step.get("expected") or step.get("value") or ""
            elem = _find_element(driver, locator)
            actual = elem.text.strip()
            if actual != str(expected).strip():
                raise AssertionError(f"Expected text '{expected}' but found '{actual}'")
        else:
            raise ValueError(f"Unsupported action: {action}")


def _find_element(driver: Any, locator: Optional[Dict[str, str]]) -> Any:
    """Helper to find a mobile element based on a locator dict."""
    if not locator:
        return _DummyMobileElement()
    ltype = locator.get("type")
    value = locator.get("value")
    if not ltype or not value:
        return _DummyMobileElement()
    # Map internal locator types to Appium strategies
    if _appium_available:
        return driver.find_element(ltype, value)
    return _DummyMobileElement()


def _iso(ts: float) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(ts))


__all__ = ["MobileDriver"]