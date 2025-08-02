"""
API MCP Implementation
----------------------

This module implements a Model Context Protocol for HTTP API testing.  It
parses natural‑language or JSON commands into HTTP requests using
`parse_api_command` and executes them with the `requests` library.  The
response status code and JSON body can be asserted via simple rules.
"""

from typing import Any, Dict

import requests

from .mcp_base import MCPBase
from ..utils.natural_language_api import execute_request
try:
    # LLM client may not be available at import time (circular import)
    from ..utils.llm_client import LLMClient  # type: ignore
except Exception:
    LLMClient = None  # type: ignore


class APIMCP(MCPBase):
    """MCP implementation for REST API interactions.

    This class delegates translation of natural language commands to an
    LLM client when configured.  If the LLM is unavailable or fails
    the translation, the original rule‑based parser is used.  It also
    respects an `expected_status` override in the step definition.
    """

    def __init__(self, config, reporter, llm_client: Any | None = None) -> None:
        super().__init__(config, reporter)
        self.llm = None
        if llm_client is not None:
            self.llm = llm_client
        elif LLMClient is not None:
            try:
                self.llm = LLMClient(config)
            except Exception:
                self.llm = None

    def _execute_step(self, step: Dict[str, Any]) -> None:
        # Step must include a 'command' field which is either plain English or JSON
        command = step.get("command")
        if not command:
            raise ValueError("API step missing 'command'")
        base_url = self.config.get("api.base_url", "")
        # Use LLM translation if available
        from ..utils.natural_language_api import parse_api_command
        if self.llm and hasattr(self.llm, "translate_api"):
            try:
                translation = self.llm.translate_api(command, base_url)
            except Exception:
                translation = None  # fall back
        else:
            translation = None
        if translation is None:
            req_obj = parse_api_command(command, base_url)
            translation = type("Tmp", (), {})()
            translation.method = req_obj.method
            translation.url = req_obj.url
            translation.headers = req_obj.headers
            translation.body = req_obj.body
            translation.expected_status = req_obj.expected_status
        expected_status = int(step.get("expected_status", translation.expected_status))
        # Execute the request
        try:
            resp = execute_request(translation)
            self.reporter.attach_text(
                f"{translation.method} {translation.url}\nHeaders: {translation.headers}\nBody: {translation.body}",
                name="api_request",
            )
            self.reporter.attach_text(
                f"Status: {resp.status_code}\nResponse: {resp.text}",
                name="api_response",
            )
            if resp.status_code != expected_status:
                raise AssertionError(f"Expected status {expected_status}, got {resp.status_code}")
            if "assert_json" in step:
                json_data = resp.json()
                for key, expected_value in step["assert_json"].items():
                    if json_data.get(key) != expected_value:
                        raise AssertionError(
                            f"Expected JSON[{key}] = {expected_value}, got {json_data.get(key)}"
                        )
        except Exception as exc:
            # Attach error and re-raise to trigger retry or alerting
            self.reporter.attach_text(f"API step error: {exc}", name="api_error")
            raise