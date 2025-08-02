"""
MCP Router
----------

The `MCPRouter` class accepts a collection of test definitions (from an
Excel sheet, BRD, JSON, etc.) and routes each test case to the
appropriate MCP based on its type.  Classification can be explicit
(`type` field on the test case) or inferred from keywords defined in
`config/config.yaml`.  The router manages the lifecycle of MCP
instances and aggregates reporting results.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Any, Dict, List, Optional

from .mcp.ui_mcp import UIMCP
from .mcp.api_mcp import APIMCP
from .mcp.mobile_mcp import MobileMCP
from .mcp.sql_mcp import SQLMCP
from .reporting.reporter import Reporter
from .utils.logger import get_logger
from .utils.alerts import send_slack_alert, send_email_alert


@dataclass
class TestCase:
    identifier: str
    steps: List[Dict[str, Any]]
    type: Optional[str] = None  # one of ui, api, mobile, sql


class MCPRouter:
    """Route test cases to their respective MCPs.

    The router is responsible for determining which MCP should execute
    a given test case.  It uses an LLM client if configured to
    classify steps; otherwise it falls back to keyword heuristics.  The
    router lazily instantiates MCP instances and optionally dispatches
    test cases via a concurrent executor.
    """

    def __init__(self, config, reporter: Reporter, executor: Any | None = None, llm_client: Any | None = None) -> None:
        self.config = config
        self.reporter = reporter
        self.logger = get_logger(self.__class__.__name__)
        # LLM client used for classification; if none provided a default
        # instance is created.  We import here to avoid circular
        # dependencies when natural_language_api.py imports LLMClient.
        if llm_client is None:
            try:
                from .utils.llm_client import LLMClient  # type: ignore
                self.llm = LLMClient(config)
            except Exception as exc:
                self.logger.error("Unable to initialise LLMClient: %s", exc)
                self.llm = None  # type: ignore
        else:
            self.llm = llm_client
        # Optional executor for parallel execution
        self.executor = executor
        # Lazy MCP instances
        self._ui_mcp: Optional[UIMCP] = None
        self._api_mcp: Optional[APIMCP] = None
        self._mobile_mcp: Optional[MobileMCP] = None
        self._sql_mcp: Optional[SQLMCP] = None

    def _classify(self, tc: TestCase) -> str:
        """Determine which MCP should execute the given test case.

        Classification is delegated to the LLM client if available.  If
        the test case specifies a type explicitly it is honoured.  On
        failure the method falls back to keyword heuristics defined in
        the configuration.
        """
        if tc.type:
            return tc.type.lower()
        combined_text = "\n".join(json.dumps(step, ensure_ascii=False) for step in tc.steps)
        # Use LLM if configured
        if hasattr(self, "llm") and self.llm:
            try:
                return self.llm.classify(combined_text)
            except Exception as exc:
                self.logger.error("LLM classification failed, falling back to heuristics: %s", exc)
        # Heuristic fallback
        keywords_map = {
            "ui": self.config.get("router.ui_keywords", []),
            "api": self.config.get("router.api_keywords", []),
            "mobile": self.config.get("router.mobile_keywords", []),
            "sql": self.config.get("router.sql_keywords", []),
        }
        combined_lower = combined_text.lower()
        for category, keywords in keywords_map.items():
            for kw in keywords:
                if kw.lower() in combined_lower:
                    return category
        return "api"

    def _get_mcp(self, mcp_type: str):
        if mcp_type == "ui":
            if self._ui_mcp is None:
                self._ui_mcp = UIMCP(self.config, self.reporter)
            return self._ui_mcp
        if mcp_type == "api":
            if self._api_mcp is None:
                self._api_mcp = APIMCP(self.config, self.reporter)
            return self._api_mcp
        if mcp_type == "mobile":
            if self._mobile_mcp is None:
                self._mobile_mcp = MobileMCP(self.config, self.reporter)
            return self._mobile_mcp
        if mcp_type == "sql":
            if self._sql_mcp is None:
                self._sql_mcp = SQLMCP(self.config, self.reporter)
            return self._sql_mcp
        raise ValueError(f"Unknown MCP type: {mcp_type}")

    def run_test_case(self, tc: TestCase) -> None:
        """Execute a single test case synchronously.

        This method performs classification, logs the routing decision,
        opens an Allure context and delegates execution to the
        corresponding MCP.  Exceptions propagate to the caller so that
        upstream code can implement retry or alerting policies.
        """
        mcp_type = self._classify(tc)
        self.logger.info("Routing test case %s to %s MCP", tc.identifier, mcp_type.upper())
        mcp = self._get_mcp(mcp_type)
        with self.reporter.start_test(tc.identifier, mcp_type):
            mcp.run(tc.steps)

    def run_all(self, test_cases: List[TestCase]) -> None:
        """Execute multiple test cases, optionally in parallel.

        If an executor has been supplied and concurrency is enabled in
        the configuration, this method will submit each test case to
        the executor.  Otherwise the cases are executed sequentially.
        """
        use_concurrency = bool(self.executor)
        if use_concurrency:
            futures = []
            for tc in test_cases:
                futures.append(self.executor.submit(self.run_test_case, tc))
            # Wait for all test cases to complete
            for f in futures:
                try:
                    f.result()
                except Exception as exc:
                    self.logger.error("Test case execution failed: %s", exc)
                    # Notify via configured alert channels
                    message = f"Test case failed: {exc}"
                    send_slack_alert(message, self.config)
                    send_email_alert("Test case failure", message, self.config)
        else:
            for tc in test_cases:
                try:
                    self.run_test_case(tc)
                except Exception as exc:
                    self.logger.error("Test case execution failed: %s", exc)
                    message = f"Test case failed: {exc}"
                    send_slack_alert(message, self.config)
                    send_email_alert("Test case failure", message, self.config)

    def close(self) -> None:
        """Close any underlying drivers held by MCPs."""
        if self._ui_mcp:
            self._ui_mcp.close()
        if self._mobile_mcp:
            self._mobile_mcp.close()
        if self._sql_mcp:
            self._sql_mcp.close()