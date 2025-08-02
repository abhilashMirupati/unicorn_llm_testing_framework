"""
Utility modules for the automation framework.

This package consolidates various helpers such as RAGAS integration,
wait logic, locator management, database utilities and webview
stabilisation.  These helpers are used by the platform drivers and
other components throughout the framework.

Importing :mod:`utils` does not have any side effects; modules should
only import heavy dependencies when required.  Callers are expected
to import the specific helper classes or functions they need.
"""

from .ragas_utils import generate_test_cases_from_brd, generate_test_cases_from_excel
from .wait_utils import wait_for_page_stable, wait_for_element_ui, wait_for_element_mobile, add_indicator
from .locator_repository import LocatorRepository
from .db_utils import Database
from .webview_utils import stabilise_webview

__all__ = [
    "generate_test_cases_from_brd",
    "generate_test_cases_from_excel",
    "wait_for_page_stable",
    "wait_for_element_ui",
    "wait_for_element_mobile",
    "add_indicator",
    "LocatorRepository",
    "Database",
    "stabilise_webview",
]