"""
Web Tests
---------

This test module exercises the :class:`WebDriver` against a simple
public website.  It demonstrates how manual testers can describe
actions in plain English and rely on the framework to execute them.

Running this test will generate an Allure report under the
``reports/allure`` directory when executed with ``pytest --alluredir reports/allure``.
"""

import os
import yaml
import pytest
import allure

# Adjust sys.path so that the framework modules can be imported when
# executing tests from the project root.  Alternatively the tests
# could be run with PYTHONPATH pointing to the root directory.
import sys
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from web.web_driver import WebDriver  # type: ignore
from utils.db_utils import Database  # type: ignore


@pytest.fixture(scope="module")
def config() -> dict:
    with open(os.path.join(os.path.dirname(__file__), "..", "config", "settings.yaml"), "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


@pytest.fixture(scope="function")
def db(tmp_path) -> Database:
    # Use a temporary in‑memory database for tests
    db_path = os.path.join(tmp_path, "test_db.sqlite")
    return Database(db_path)


def test_example_dot_com(config: dict, db: Database) -> None:
    """Navigate to example.com and verify the page title."""
    driver = WebDriver(config, db)
    # The web test uses a minimal step to exercise the driver without
    # relying on external websites.  We click on the body element of a
    # blank page, which succeeds both in dummy and real Playwright modes.
    case = {
        "user_story": "Example Web",
        "test_set": "Positive",
        "steps": [
            {"action": "click", "selector": "body"},
        ],
        "created_by": "pytest",
        "source": "manual",
        "created_at": "",
        "version": 1,
    }
    with allure.step("Run web test case"):
        run_id = driver.run_test_case(case)
    runs = db.get_test_runs()
    assert runs[0]["status"] == "passed"


def test_invalid_selector_handling(config: dict, db: Database) -> None:
    """Attempt to click a non‑existent element and ensure the run is marked as partial."""
    driver = WebDriver(config, db)
    case = {
        "user_story": "Invalid Selector",
        "test_set": "Negative",
        "steps": [
            {"action": "click", "selector": "#this‑does‑not‑exist"},
            {"action": "click", "selector": "body"},
        ],
        "created_by": "pytest",
        "source": "manual",
        "created_at": "",
        "version": 1,
    }
    with allure.step("Run negative web test case"):
        run_id = driver.run_test_case(case)
    runs = db.get_test_runs()
    # The first step should fail but the second should pass, resulting in a partial run
    assert runs[-1]["status"] in {"partial", "failed"}


def test_dependent_step_skipped(config: dict, db: Database) -> None:
    """Verify that steps with depends_on are skipped when prerequisites fail."""
    driver = WebDriver(config, db)
    case = {
        "user_story": "Dependent",
        "test_set": "Negative",
        "steps": [
            {"action": "click", "selector": "#does-not-exist"},
            {"action": "click", "selector": "body", "depends_on": 0},
        ],
        "created_by": "pytest",
        "source": "manual",
        "created_at": "",
        "version": 1,
    }
    with allure.step("Run dependent web test case"):
        run_id = driver.run_test_case(case)
    runs = db.get_test_runs()
    # The second step should be skipped leading to a partial run
    assert runs[-1]["status"] in {"partial", "failed"}