"""
Natural Language to API Request Translator
-----------------------------------------

This module contains helper functions that convert English phrases or
structured JSON (Postman collections, Swagger fragments) into
executable HTTP requests.  The translator covers a limited set of
patterns to demonstrate the concept of LLM‑driven API generation.
"""

import json
import logging
import re
from dataclasses import dataclass
from typing import Any, Dict, Optional

import requests

logger = logging.getLogger(__name__)


@dataclass
class APIRequest:
    method: str
    url: str
    headers: Optional[Dict[str, str]]
    body: Optional[Any]
    expected_status: int = 200


def parse_api_command(command: str, base_url: str = "") -> APIRequest:
    """Parse a natural language or JSON API command into an APIRequest.

    The following forms are supported:

    * JSON strings with keys `method`, `url`, `headers`, `body`, and
      optional `expected_status`.
    * English commands of the form "GET /endpoint", "POST to /endpoint with
      json { ... }", etc.  If the command does not include a full URL, the
      `base_url` will be prepended.
    """
    command = command.strip()
    # If the command looks like JSON, parse it directly
    if command.startswith("{") or command.startswith("["):
        try:
            data = json.loads(command)
            method = data.get("method", "GET").upper()
            url = data.get("url", "")
            headers = data.get("headers")
            body = data.get("body")
            expected_status = data.get("expected_status", 200)
            if base_url and not url.startswith("http"):
                url = base_url.rstrip("/") + "/" + url.lstrip("/")
            return APIRequest(method, url, headers, body, expected_status)
        except Exception as exc:
            logger.warning("Failed to parse JSON API command: %s", exc)

    # Parse simple English commands
    # e.g. "GET /users", "POST to /users with json {\"name\": \"John\"}".
    m = re.match(r"(get|post|put|delete)\s+(.+)", command, re.IGNORECASE)
    if m:
        method = m.group(1).upper()
        remainder = m.group(2).strip()
        url = ""
        headers: Dict[str, str] = {}
        body: Optional[Any] = None
        expected_status = 200

        # Extract URL and optional JSON body
        # Pattern: "/endpoint" or "to /endpoint with json {...}".
        if " with json" in remainder:
            url_part, json_part = remainder.split(" with json", 1)
            url = url_part.strip()
            try:
                body = json.loads(json_part.strip())
                headers["Content-Type"] = "application/json"
            except json.JSONDecodeError:
                logger.error("Invalid JSON body in command: %s", json_part)
        else:
            url = remainder

        # Prepend base URL if not absolute
        if base_url and not url.startswith("http"):
            url = base_url.rstrip("/") + "/" + url.lstrip("/")
        return APIRequest(method, url, headers or None, body, expected_status)

    # Fallback: treat the entire string as a GET request path
    if base_url and not command.startswith("http"):
        url = base_url.rstrip("/") + "/" + command.lstrip("/")
        return APIRequest("GET", url, None, None, 200)
    return APIRequest("GET", command, None, None, 200)


def execute_request(req: APIRequest) -> requests.Response:
    """Execute an APIRequest using the `requests` library."""
    method_func = getattr(requests, req.method.lower(), None)
    if not method_func:
        raise ValueError(f"Unsupported HTTP method: {req.method}")
    resp = method_func(req.url, headers=req.headers, json=req.body)
    return resp


__all__ = ["APIRequest", "parse_api_command", "execute_request"]