"""
Enterprise Automation Framework
==============================

This package provides a modular, LLM‑native test automation framework that
implements the Model Context Protocol (MCP) pattern across UI, API, Mobile
and SQL domains.  The top‑level exports include the configuration loader,
router, versioning manager and MCP implementations.

Modules
-------

``mcp_router``
    Central dispatcher that directs test cases to UI, API, Mobile or SQL MCPs.

``mcp``
    Subpackage containing implementations for each MCP type.

``versioning``
    Subpackage responsible for managing versioned test sets and deduplication.

``reporting``
    Subpackage that wraps Allure reporting functions.

``dashboard``
    Simple FastAPI application exposing a REST/HTML interface for managing
    test sets and launching runs.
"""

from .config import Config
from .mcp_router import MCPRouter
from .versioning.version_manager import VersionManager
from .reporting.reporter import Reporter

__all__ = [
    "Config",
    "MCPRouter",
    "VersionManager",
    "Reporter",
]