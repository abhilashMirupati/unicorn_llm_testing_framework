"""
Audit Logging
-------------

This module implements a simple audit log for the dashboard
application.  Each time a user performs a sensitive action (such as
logging in, viewing a page, triggering a test run or managing
accounts) an entry is written to a SQLite table.  Administrators can
review the audit log via the dashboard to monitor activity and
investigate issues.  The audit log is stored in the same database as
the version manager by default.

The schema is deliberately minimal: an auto‑incrementing ID, the
timestamp of the event (ISO 8601), the username associated with the
request and a free‑form text field describing the action.  Additional
fields can be added later without changing the API.  See
``AuditLogger.log()`` for usage.

Example::

    from .audit import AuditLogger
    audit = AuditLogger(config)
    audit.log(user="admin", action="Viewed versions page for story X")

The audit logger gracefully handles missing or invalid database
connections and will fall back to printing to the configured logger if
the database cannot be updated.  This ensures that audit events are
never silently lost.
"""

from __future__ import annotations

import datetime as _dt
import sqlite3
from pathlib import Path
from typing import Any, Dict, List

from .logger import get_logger


class AuditLogger:
    """Persist audit events to a SQLite database."""

    def __init__(self, config) -> None:
        self.config = config
        self.logger = get_logger(self.__class__.__name__)
        db_url = config.get("database.url", "sqlite:///./test_sets.db")
        if db_url.startswith("sqlite:///"):
            db_path = db_url[len("sqlite:///"):]
        else:
            db_path = db_url
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        try:
            # Use check_same_thread=False so the SQLite connection can be
            # shared across threads (FastAPI runs endpoints in a threadpool).
            self.conn = sqlite3.connect(db_path, check_same_thread=False)
            self.cursor = self.conn.cursor()
            self._ensure_schema()
        except Exception as exc:
            # If we cannot connect to the database, fallback to in‑memory list
            self.logger.error("AuditLogger failed to initialise: %s", exc)
            self.conn = None  # type: ignore
            self.cursor = None  # type: ignore
            self._fallback: List[Dict[str, Any]] = []

    def _ensure_schema(self) -> None:
        if not self.cursor:
            return
        self.cursor.execute(
            """CREATE TABLE IF NOT EXISTS audit_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                username TEXT NOT NULL,
                action TEXT NOT NULL
            )"""
        )
        self.conn.commit()

    def log(self, username: str, action: str) -> None:
        """Record an audit event.

        This method inserts a new row into the audit_log table with the
        current timestamp, username and action description.  If the
        database is unavailable, events are appended to an in‑memory
        buffer and logged to the console.
        """
        timestamp = _dt.datetime.utcnow().isoformat()
        try:
            if self.cursor:
                self.cursor.execute(
                    "INSERT INTO audit_log (timestamp, username, action) VALUES (?,?,?)",
                    (timestamp, username, action),
                )
                self.conn.commit()
            else:
                # Fallback: store in memory and log
                self._fallback.append({"timestamp": timestamp, "username": username, "action": action})  # type: ignore
                self.logger.info("AUDIT %s %s: %s", timestamp, username, action)
        except Exception as exc:
            self.logger.error("Failed to write audit log: %s", exc)
            # Fallback: log to console
            self.logger.info("AUDIT %s %s: %s", timestamp, username, action)

    def list_events(self, limit: int = 100) -> List[Dict[str, Any]]:
        """Return the most recent audit events up to `limit`.

        If the database is unavailable the in‑memory fallback events
        are returned.  Results are ordered by descending ID (most
        recent first).
        """
        try:
            if self.cursor:
                self.cursor.execute(
                    "SELECT timestamp, username, action FROM audit_log ORDER BY id DESC LIMIT ?",
                    (limit,),
                )
                rows = self.cursor.fetchall()
                return [
                    {"timestamp": row[0], "username": row[1], "action": row[2]}
                    for row in rows
                ]
        except Exception as exc:
            self.logger.error("Failed to read audit log: %s", exc)
        # Fallback
        return list(reversed(getattr(self, "_fallback", [])))  # type: ignore

    def close(self) -> None:
        if self.conn:
            try:
                self.conn.close()
            except Exception:
                pass


__all__ = ["AuditLogger"]