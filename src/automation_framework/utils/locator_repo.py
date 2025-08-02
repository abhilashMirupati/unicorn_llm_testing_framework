"""
Locator Repository
------------------

This module implements a simple persistent repository for element
locators.  Locators are looked up based on a *step key*, which is a
semi‑stable representation of the test step (for example a
combination of the action and a human description of the element).  A
locator consists of its type (CSS selector, XPath, accessibility ID,
etc.) and the value needed to locate the element.  When a locator
changes (for example because the underlying page was updated) the new
locator is stored as a new version and the old one is marked as
inactive.  Consumers can request the most recent active locator for a
step key and context (ui or mobile).  Internally a SQLite database
is used to persist records across test runs.

The repository schema is designed for extensibility: additional
columns can be added without breaking existing records.  Timestamps
are stored in ISO‑8601 format and version numbers increment
monotonically for each (context, step key) pair.  All operations
within this module are thread‑safe when using the same instance of
``LocatorRepo`` because SQLite serialises writes; however concurrent
access from multiple processes is not supported.

Example usage::

    repo = LocatorRepo(config)
    key = repo.compute_step_key({"action": "click", "element": "Login"})
    loc = repo.get_locator("ui", key)
    if loc is None:
        # derive a new locator via heuristics or LLM
        new_loc = {"type": "css", "value": "button:has-text('Login')"}
        repo.add_locator("ui", key, new_loc)
        loc = new_loc
    # use loc["type"] and loc["value"] to perform the action

This module should be considered an infrastructure component; higher
level code such as MCPs and wait utilities are responsible for
interpreting the stored locators and performing the actual UI or
mobile interactions.
"""

from __future__ import annotations

import datetime as _dt
import json
import sqlite3
from pathlib import Path
from typing import Any, Dict, Optional

from .logger import get_logger


class LocatorRepo:
    """Persist and retrieve locators for UI and mobile steps.

    The repository stores a mapping of ``(context, step_key)`` to one
    or more versions of locators.  Only the most recent active
    locator is returned by :meth:`get_locator`.  When a new locator
    version is added via :meth:`add_locator`, the previous active
    locator (if any) is marked as inactive.  Older versions remain in
    the database for auditing and rollback purposes.  Consumers may
    query the entire history using :meth:`list_locators`.
    """

    def __init__(self, config: Any, db_path: Optional[str] = None) -> None:
        self.logger = get_logger(self.__class__.__name__)
        # Determine the path to the locator repository database.  A
        # value can be provided in the configuration or passed
        # explicitly.  If neither is provided the default is
        # ``locators.db`` in the project root.  When using a SQLite URL
        # (e.g. ``sqlite:///./locators.db``) the prefix is stripped.
        conf_path = config.get("locator_repo.path") if hasattr(config, "get") else None
        db_path = db_path or conf_path or "./locators.db"
        if db_path.startswith("sqlite:///"):
            db_file = db_path[len("sqlite:///"):]
        else:
            db_file = db_path
        Path(db_file).parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(db_file)
        self.cursor = self.conn.cursor()
        self._ensure_schema()

    def _ensure_schema(self) -> None:
        """Create the locator table if it does not exist."""
        self.cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS locators (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                context TEXT NOT NULL,
                step_key TEXT NOT NULL,
                locator_type TEXT NOT NULL,
                locator_value TEXT NOT NULL,
                version INTEGER NOT NULL,
                is_active INTEGER NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        self.cursor.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS idx_locators_active
            ON locators (context, step_key, is_active)
            WHERE is_active = 1
            """
        )
        self.conn.commit()

    def compute_step_key(self, step: Dict[str, Any]) -> str:
        """Compute a stable key identifying a test step.

        The default implementation combines the action with the most
        descriptive field found in the step.  It prefers ``selector`` or
        ``locator`` fields (since those uniquely identify elements) but
        falls back to ``element``, ``text`` or other fields if needed.
        As a final fallback the entire step dictionary is serialised.
        """
        action = step.get("action", "unknown")
        # Prioritise explicit selector/locator definitions
        if "selector" in step:
            return f"{action}:{step['selector']}"
        if "locator" in step:
            try:
                loc_json = json.dumps(step["locator"], sort_keys=True)
            except Exception:
                loc_json = str(step["locator"])
            return f"{action}:{loc_json}"
        # Use element or text fields for natural language descriptions
        for key in ("element", "label", "text", "value", "placeholder"):
            if key in step:
                return f"{action}:{step[key]}"
        # Fallback to serialising the entire step
        try:
            step_json = json.dumps({k: step[k] for k in sorted(step)}, sort_keys=True)
        except Exception:
            step_json = str(step)
        return f"{action}:{step_json}"

    def get_locator(self, context: str, step_key: str) -> Optional[Dict[str, Any]]:
        """Return the most recent active locator for the given context and step key.

        Returns a dictionary with ``type`` and ``value`` keys or ``None``
        if no locator is stored.  Context should be ``"ui"`` or
        ``"mobile"``.  If multiple active locators exist (which should
        not happen due to the unique index) the one with the highest
        version number is returned.
        """
        self.cursor.execute(
            """
            SELECT locator_type, locator_value
            FROM locators
            WHERE context = ? AND step_key = ? AND is_active = 1
            ORDER BY version DESC
            LIMIT 1
            """,
            (context, step_key),
        )
        row = self.cursor.fetchone()
        if not row:
            return None
        return {"type": row[0], "value": row[1]}

    def add_locator(self, context: str, step_key: str, locator: Dict[str, str]) -> None:
        """Insert a new locator version and mark previous active ones inactive.

        ``locator`` must have ``type`` and ``value`` keys.  A new
        version number is computed by incrementing the highest existing
        version for the (context, step_key) pair.  The created and
        updated timestamps are recorded.  The old active record, if
        present, is marked inactive.
        """
        locator_type = locator.get("type")
        locator_value = locator.get("value")
        if not locator_type or not locator_value:
            raise ValueError("Locator must have 'type' and 'value' fields")
        # Deactivate previous active locator (if any)
        self.cursor.execute(
            "UPDATE locators SET is_active = 0, updated_at = ? WHERE context = ? AND step_key = ? AND is_active = 1",
            (_dt.datetime.now().isoformat(), context, step_key),
        )
        # Determine next version
        self.cursor.execute(
            "SELECT MAX(version) FROM locators WHERE context = ? AND step_key = ?",
            (context, step_key),
        )
        row = self.cursor.fetchone()
        next_version = (row[0] + 1) if row and row[0] is not None else 1
        now = _dt.datetime.now().isoformat()
        self.cursor.execute(
            """
            INSERT INTO locators (context, step_key, locator_type, locator_value,
                                  version, is_active, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, 1, ?, ?)
            """,
            (context, step_key, locator_type, locator_value, next_version, now, now),
        )
        self.conn.commit()
        self.logger.info(
            "Recorded locator for context=%s, key=%s (type=%s, value=%s, version=%s)",
            context,
            step_key,
            locator_type,
            locator_value,
            next_version,
        )

    def list_locators(self, context: Optional[str] = None, step_key: Optional[str] = None) -> list[Dict[str, Any]]:
        """List all locators matching the optional filters.

        Returns a list of dictionaries containing locator metadata.
        ``context`` may be one of ``"ui"`` or ``"mobile"``; when
        omitted all contexts are returned.  ``step_key`` filters to a
        specific step.  The results are sorted by context, step key and
        descending version.
        """
        query = "SELECT context, step_key, locator_type, locator_value, version, is_active, created_at, updated_at FROM locators"
        clauses = []
        params: list[Any] = []
        if context:
            clauses.append("context = ?")
            params.append(context)
        if step_key:
            clauses.append("step_key = ?")
            params.append(step_key)
        if clauses:
            query += " WHERE " + " AND ".join(clauses)
        query += " ORDER BY context, step_key, version DESC"
        self.cursor.execute(query, params)
        rows = self.cursor.fetchall()
        return [
            {
                "context": r[0],
                "step_key": r[1],
                "type": r[2],
                "value": r[3],
                "version": r[4],
                "active": bool(r[5]),
                "created_at": r[6],
                "updated_at": r[7],
            }
            for r in rows
        ]

    def close(self) -> None:
        """Close the underlying database connection."""
        try:
            self.conn.commit()
            self.conn.close()
        except Exception:
            pass

    def __del__(self) -> None:
        try:
            self.close()
        except Exception:
            pass


__all__ = ["LocatorRepo"]