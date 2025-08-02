"""
Mobile Tests
------------

This module exercises the :class:`MobileDriver` in dummy mode.  Since
Appium is not typically available in the execution environment these
tests simply verify that the driver can execute steps without raising
exceptions and that results are recorded appropriately.
"""

import os
import sys
import yaml
import pytest
import allure

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from mobile.mobile_driver import MobileDriver  # type: ignore
from utils.db_utils import Database  # type: ignore


@pytest.fixture(scope="module")
def config() -> dict:
    with open(os.path.join(os.path.dirname(__file__), "..", "config", "settings.yaml"), "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


@pytest.fixture(scope="function")
def db(tmp_path) -> Database:
    db_path = os.path.join(tmp_path, "test_db.sqlite")
    return Database(db_path)


def test_dummy_mobile(config: dict, db: Database) -> None:
    """Run a mobile test in dummy mode."""
    driver = MobileDriver(config, db)
    case = {
        "user_story": "Mobile",
        "test_set": "Positive",
        "steps": [
            {"action": "tap", "locator": {"type": "accessibility_id", "value": "Login"}},
            {"action": "fill", "locator": {"type": "accessibility_id", "value": "Username"}, "value": "user"},
            {"action": "fill", "locator": {"type": "accessibility_id", "value": "Password"}, "value": "pass"},
            {"action": "assert_text", "locator": {"type": "accessibility_id", "value": "Status"}, "expected": ""},
        ],
        "created_by": "pytest",
        "source": "manual",
        "created_at": "",
        "version": 1,
    }
    with allure.step("Run mobile test case"):
        run_id = driver.run_test_case(case)
    runs = db.get_test_runs()
    assert runs[0]["status"] == "passed"


def test_missing_locator_skipped(config: dict, db: Database) -> None:
    """Verify that a mobile step lacking a locator is skipped rather than failing the entire run."""
    driver = MobileDriver(config, db)
    case = {
        "user_story": "Missing Locator",
        "test_set": "Negative",
        "steps": [
            {"action": "tap"},  # missing locator
            {"action": "tap", "locator": {"type": "accessibility_id", "value": "Login"}},
        ],
        "created_by": "pytest",
        "source": "manual",
        "created_at": "",
        "version": 1,
    }
    with allure.step("Run mobile test with missing locator"):
        run_id = driver.run_test_case(case)
    runs = db.get_test_runs()
    # At least one step is skipped, so the overall status should be partial
    assert runs[-1]["status"] in {"partial", "skipped"}


def test_mobile_dependent_step(config: dict, db: Database) -> None:
    """Ensure mobile driver skips dependent steps when prerequisite fails."""
    driver = MobileDriver(config, db)
    case = {
        "user_story": "Mobile Dependent",
        "test_set": "Negative",
        "steps": [
            {"action": "tap"},  # missing locator will cause skip
            {"action": "tap", "locator": {"type": "accessibility_id", "value": "Login"}, "depends_on": 0},
        ],
        "created_by": "pytest",
        "source": "manual",
        "created_at": "",
        "version": 1,
    }
    with allure.step("Run mobile dependent test case"):
        run_id = driver.run_test_case(case)
    runs = db.get_test_runs()
    assert runs[-1]["status"] in {"partial", "skipped"}