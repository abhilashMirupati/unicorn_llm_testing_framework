"""
API Driver
----------

This module defines :class:`APIDriver`, a helper for executing API
tests described in plain English.  Each test step is translated into a
structured request using the LLM agent or a deterministic parser and
then executed with the ``requests`` library.  Results are recorded in
the database at both the run and step level.
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any, Dict, Optional

import requests

from ..utils.db_utils import Database
from ..llm_integration.llm_agent import LLMAgent, APIRequest


class APIDriver:
    """Execute API test cases described in natural language."""

    def __init__(self, config: Any, db: Database) -> None:
        self.config = config
        self.db = db
        self.llm = LLMAgent(config)
        # Precompute base URLs from config
        try:
            self.base_urls = config.get("api", {}).get("base_urls", {})  # type: ignore
        except Exception:
            self.base_urls = {}

    def run_test_case(self, case: Dict[str, Any]) -> int:
        """Execute an API test case and record results.

        The API driver executes each step sequentially and records
        individual outcomes.  Missing commands are reported as skipped.
        A run is considered ``passed`` only if all steps pass.  If some
        steps fail while others pass the run status becomes ``partial``.
        """
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
        return run_id

    def _execute_step(self, step: Dict[str, Any]) -> None:
        """Execute an individual API step."""
        # Steps may specify a natural language command in 'command' or 'text'
        command = step.get("command") or step.get("text") or step.get("description")
        if not command:
            raise ValueError("API step requires a 'command' or 'text' field")
        # Determine base URL.  If the step specifies a base key use it; otherwise default
        base_key = step.get("base") or "default"
        base_url = self.base_urls.get(base_key, "")
        req: APIRequest = self.llm.translate_api(command, base_url)
        method = req.method or "GET"
        url = req.url
        headers = req.headers or {}
        body = req.body
        # Allow the test case to override expected status per step
        expected_status = step.get("expected_status", req.expected_status or 200)
        # Execute using requests
        response = requests.request(method=method, url=url, headers=headers, json=body)
        if response.status_code != expected_status:
            raise AssertionError(
                f"Expected status {expected_status} but got {response.status_code} for {method} {url}"
            )
        # Optionally validate response body
        if "expected_body" in step:
            expected_body = step["expected_body"]
            actual_json: Any = None
            try:
                actual_json = response.json()
            except Exception:
                actual_json = response.text
            if isinstance(expected_body, dict):
                # Check that all key/value pairs exist in the actual response
                for k, v in expected_body.items():
                    if not isinstance(actual_json, dict) or actual_json.get(k) != v:  # type: ignore[union-attr]
                        raise AssertionError(f"Expected response field {k}={v} but got {actual_json.get(k) if isinstance(actual_json, dict) else 'N/A'}")
            else:
                if str(expected_body) not in response.text:
                    raise AssertionError(f"Expected body to contain {expected_body} but got {response.text}")
        # Swagger mismatch handling via snapshot hash
        if step.get("snapshot_hash"):
            import hashlib
            body_bytes = response.content or b""
            digest = hashlib.sha256(body_bytes).hexdigest()
            if digest != step["snapshot_hash"]:
                raise AssertionError(
                    f"Swagger snapshot hash mismatch: expected {step['snapshot_hash']} but got {digest}"
                )


def _iso(ts: float) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(ts))


__all__ = ["APIDriver"]