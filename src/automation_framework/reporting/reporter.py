"""
Allure Reporting Wrapper
-----------------------

This module wraps the Allure Python API to make reporting easier from
within the framework.  It exposes a `Reporter` class that manages test
contexts, attaches logs, screenshots and raw bytes, and ensures the
results directory exists.  The Allure integration is optional; if
Allure is not installed the reporter will still log messages but
attachments will be no‑ops.
"""

from __future__ import annotations

import os
from contextlib import contextmanager
from pathlib import Path
from typing import Optional

from ..utils.logger import get_logger

try:
    import allure  # type: ignore
except ImportError:
    allure = None  # type: ignore


class Reporter:
    """Wrapper around Allure for attaching evidence and starting tests."""

    def __init__(self, config) -> None:
        self.config = config
        self.logger = get_logger(self.__class__.__name__)
        self.results_dir = Path(config.get("allure.results_dir", "reports"))
        self.results_dir.mkdir(parents=True, exist_ok=True)
        if allure:
            os.environ["ALLURE_RESULTS_DIR"] = str(self.results_dir)

    @contextmanager
    def start_test(self, test_name: str, mcp_type: str):
        """Context manager to start an Allure test case."""
        if allure:
            with allure.step(f"{mcp_type.upper()} Test: {test_name}"):
                yield
        else:
            self.logger.info("START TEST %s (%s)", test_name, mcp_type)
            try:
                yield
            finally:
                self.logger.info("END TEST %s (%s)", test_name, mcp_type)

    def attach_text(self, text: str, name: str = "attachment") -> None:
        """Attach plain text to the report."""
        if allure:
            allure.attach(text, name=name, attachment_type=allure.attachment_type.TEXT)
        else:
            self.logger.debug("Text attachment %s:\n%s", name, text)

    def attach_bytes(self, data: bytes, name: str = "attachment", extension: str = "bin") -> None:
        """Attach binary data to the report."""
        if allure:
            allure.attach(data, name=name, attachment_type=allure.attachment_type.PNG)
        else:
            self.logger.debug("Binary attachment %s (%d bytes)", name, len(data))
