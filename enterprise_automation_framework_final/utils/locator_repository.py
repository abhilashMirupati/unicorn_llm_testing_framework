"""
Locator Repository
------------------

This module implements a persistent repository for element locators.
Locators are stored in a SQLite database keyed off the test step and
execution context (``ui`` or ``mobile``).  When an element changes
(for example because the underlying UI was updated) a new locator
version may be added; older versions remain in the database for
auditing and rollback purposes but are marked inactive.  Consumers
should always call :meth:`get_locator` to retrieve the most recent
active locator.

The repository schema is created on first use.  Each record stores the
locator type (e.g. ``css``, ``xpath``, ``accessibility_id``) and
locator value along with a monotonically increasing version number.
Multiple versions may exist for the same (context, step key) pair but
only one can be active at a time.
"""

from __future__ import annotations

import datetime as _dt
import json
import logging
import sqlite3
from pathlib import Path
from typing import Any, Dict, Optional


class LocatorRepository:
    """Persist and retrieve locators for UI and mobile steps.

    A ``LocatorRepository`` instance encapsulates a SQLite connection
    and provides methods to compute stable step keys, retrieve active
    locators and insert new locator versions.  The database file is
    determined from the configuration passed to the constructor or
    defaults to ``locators_repo/locators.db`` relative to the project
    root.
    """

    def __init__(self, config: Any, db_path: Optional[str] = None) -> None:
        self.logger = logging.getLogger(self.__class__.__name__)
        # Determine database path from config or explicit parameter
        conf_path = None
        try:
            conf_path = config.get("locator_repo", {}).get("path")  # type: ignore[assignment]
        except Exception:
            conf_path = None
        db_path = db_path or conf_path or "locators_repo/locators.db"
        # Strip sqlite:/// prefix if present
        if db_path.startswith("sqlite:///"):
            db_file = db_path[len("sqlite:///") :]
        else:
            db_file = db_path
        Path(db_file).parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(db_file)
        self.cursor = self.conn.cursor()
        self._ensure_schema()

    def _ensure_schema(self) -> None:
        """Create the database schema if necessary."""
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

    @staticmethod
    def compute_step_key(step: Dict[str, Any]) -> str:
        """Compute a stable key identifying a test step.

        The default implementation combines the action with the most
        descriptive field found in the step.  It prefers explicit
        ``selector`` or ``locator`` fields and falls back to other
        descriptive keys.  As a last resort the entire step dictionary
        is serialised.
        """
        action = step.get("action", "unknown")
        # Prefer explicit selector/locator definitions
        if "selector" in step:
            return f"{action}:{step['selector']}"
        if "locator" in step:
            try:
                loc_json = json.dumps(step["locator"], sort_keys=True)
            except Exception:
                loc_json = str(step["locator"])
            return f"{action}:{loc_json}"
        # Use human description fields
        for key in ("element", "label", "text", "value", "placeholder", "target"):
            if key in step:
                return f"{action}:{step[key]}"
        # Fallback: serialise the entire step
        try:
            step_json = json.dumps({k: step[k] for k in sorted(step)}, sort_keys=True)
        except Exception:
            step_json = str(step)
        return f"{action}:{step_json}"

    def get_locator(self, context: str, step_key: str) -> Optional[Dict[str, Any]]:
        """Return the most recent active locator for the given key and context.

        Returns a dictionary with ``type`` and ``value`` keys or
        ``None`` if no locator is stored.  If multiple active locators
        somehow exist (which should not happen due to the unique index)
        the newest is returned.
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
        """Insert a new locator version and mark previous active ones inactive."""
        locator_type = locator.get("type")
        locator_value = locator.get("value")
        if not locator_type or not locator_value:
            raise ValueError("Locator must have 'type' and 'value' fields")
        # Deactivate previous active locator
        now = _dt.datetime.utcnow().isoformat()
        self.cursor.execute(
            "UPDATE locators SET is_active = 0, updated_at = ? WHERE context = ? AND step_key = ? AND is_active = 1",
            (now, context, step_key),
        )
        # Determine next version
        self.cursor.execute(
            "SELECT MAX(version) FROM locators WHERE context = ? AND step_key = ?",
            (context, step_key),
        )
        row = self.cursor.fetchone()
        next_version = (row[0] + 1) if row and row[0] is not None else 1
        self.cursor.execute(
            """
            INSERT INTO locators (
                context, step_key, locator_type, locator_value,
                version, is_active, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, 1, ?, ?)
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


__all__ = ["LocatorRepository"]