"""
Database Utilities
------------------

This module encapsulates SQLite operations used by the automation
framework.  It defines a :class:`Database` class that manages
persistent storage for test cases, test steps, test runs and run
steps.  Using a dedicated helper class isolates SQL logic from the
drivers and makes it easier to evolve the schema over time.

The schema consists of the following tables:

* ``test_cases`` – high level descriptions of test cases.  Each case
  belongs to a user story and test set and has a version.
* ``test_steps`` – individual steps belonging to a test case.  Steps
  are stored in the order they should be executed.
* ``test_runs`` – execution records for a test case.  Each run stores
  its status (pass/fail/skip), timestamps and an optional error message.
* ``run_steps`` – step level results for a particular run, including
  status and messages.
* ``versions`` – version history for test cases keyed by user story
  and test set.  This table supports rollbacks and audit trails.

All timestamps are stored in UTC ISO‑8601 format.  Caller code is
responsible for converting to local timezones if required.
"""

from __future__ import annotations

import datetime as _dt
import logging
import sqlite3
from typing import Any, Dict, Iterable, List, Optional, Tuple


class Database:
    """Encapsulate SQLite access for the automation framework."""

    def __init__(self, db_path: str) -> None:
        self.logger = logging.getLogger(self.__class__.__name__)
        self.conn = sqlite3.connect(db_path)
        # enable foreign keys
        self.conn.execute("PRAGMA foreign_keys = ON")
        self._ensure_schema()

    def _ensure_schema(self) -> None:
        """Create the database schema if it does not exist."""
        cursor = self.conn.cursor()
        # Table storing test cases
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS test_cases (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_story TEXT NOT NULL,
                test_set TEXT NOT NULL,
                description TEXT NOT NULL,
                created_by TEXT NOT NULL,
                source TEXT NOT NULL,
                created_at TEXT NOT NULL,
                version INTEGER NOT NULL
            )
            """
        )
        # Steps belonging to test cases
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS test_steps (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                test_case_id INTEGER NOT NULL,
                step_index INTEGER NOT NULL,
                action TEXT NOT NULL,
                target TEXT,
                input_data TEXT,
                expected TEXT,
                created_at TEXT NOT NULL,
                FOREIGN KEY (test_case_id) REFERENCES test_cases(id) ON DELETE CASCADE
            )
            """
        )
        # Test run records
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS test_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                test_case_id INTEGER NOT NULL,
                status TEXT NOT NULL,
                started_at TEXT NOT NULL,
                ended_at TEXT NOT NULL,
                error_message TEXT,
                FOREIGN KEY (test_case_id) REFERENCES test_cases(id) ON DELETE CASCADE
            )
            """
        )
        # Step results for each run
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS run_steps (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                test_run_id INTEGER NOT NULL,
                step_index INTEGER NOT NULL,
                status TEXT NOT NULL,
                message TEXT,
                started_at TEXT NOT NULL,
                ended_at TEXT NOT NULL,
                FOREIGN KEY (test_run_id) REFERENCES test_runs(id) ON DELETE CASCADE
            )
            """
        )
        # Version history for test cases
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS versions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_story TEXT NOT NULL,
                test_set TEXT NOT NULL,
                version INTEGER NOT NULL,
                source TEXT NOT NULL,
                file_name TEXT,
                comments TEXT,
                created_at TEXT NOT NULL
            )
            """
        )
        self.conn.commit()

    # Utility function to get current time
    def _now(self) -> str:
        return _dt.datetime.utcnow().isoformat()

    # CRUD operations for test cases
    def add_test_case(self, case: Dict[str, Any]) -> int:
        """Insert a new test case and its steps into the database.

        :param case: A dictionary with keys ``user_story``, ``test_set``,
            ``steps``, ``created_by``, ``source``, ``created_at`` and
            ``version``.  Steps should be a list of dictionaries with
            ``action``, ``target``, optional ``input_data`` and
            optional ``expected``.
        :returns: The database ID of the inserted test case.
        """
        cursor = self.conn.cursor()
        cursor.execute(
            """
            INSERT INTO test_cases (
                user_story, test_set, description, created_by, source, created_at, version
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                case["user_story"],
                case["test_set"],
                "; ".join(f"{step.get('action','')} {step.get('target', '')}".strip() for step in case.get("steps", [])),
                case["created_by"],
                case["source"],
                case.get("created_at", self._now()),
                case.get("version", 1),
            ),
        )
        test_case_id = cursor.lastrowid
        # Insert steps
        for idx, step in enumerate(case.get("steps", [])):
            cursor.execute(
                """
                INSERT INTO test_steps (
                    test_case_id, step_index, action, target, input_data, expected, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    test_case_id,
                    idx,
                    step.get("action", ""),
                    step.get("target"),
                    step.get("input_data"),
                    step.get("expected"),
                    case.get("created_at", self._now()),
                ),
            )
        self.conn.commit()
        return test_case_id

    def get_test_cases(self) -> List[Dict[str, Any]]:
        """Return a list of all test cases in the database."""
        cursor = self.conn.cursor()
        cursor.execute(
            "SELECT id, user_story, test_set, description, created_by, source, created_at, version FROM test_cases"
        )
        rows = cursor.fetchall()
        cases: List[Dict[str, Any]] = []
        for row in rows:
            cases.append(
                {
                    "id": row[0],
                    "user_story": row[1],
                    "test_set": row[2],
                    "description": row[3],
                    "created_by": row[4],
                    "source": row[5],
                    "created_at": row[6],
                    "version": row[7],
                }
            )
        return cases

    # Test run operations
    def add_test_run(self, test_case_id: int, status: str, started_at: str, ended_at: str, error_message: Optional[str] = None) -> int:
        """Insert a test run record.

        :returns: The database ID of the inserted run.
        """
        cursor = self.conn.cursor()
        cursor.execute(
            """
            INSERT INTO test_runs (test_case_id, status, started_at, ended_at, error_message)
            VALUES (?, ?, ?, ?, ?)
            """,
            (test_case_id, status, started_at, ended_at, error_message),
        )
        run_id = cursor.lastrowid
        self.conn.commit()
        return run_id

    def add_run_step(self, test_run_id: int, step_index: int, status: str, message: Optional[str], started_at: str, ended_at: str) -> None:
        """Record the result of a single step during a test run."""
        cursor = self.conn.cursor()
        cursor.execute(
            """
            INSERT INTO run_steps (test_run_id, step_index, status, message, started_at, ended_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (test_run_id, step_index, status, message, started_at, ended_at),
        )
        self.conn.commit()

    def get_test_runs(self, test_case_id: Optional[int] = None) -> List[Dict[str, Any]]:
        """Return test run records, optionally filtered by test case."""
        cursor = self.conn.cursor()
        if test_case_id is None:
            cursor.execute(
                "SELECT id, test_case_id, status, started_at, ended_at, error_message FROM test_runs"
            )
        else:
            cursor.execute(
                "SELECT id, test_case_id, status, started_at, ended_at, error_message FROM test_runs WHERE test_case_id = ?",
                (test_case_id,),
            )
        rows = cursor.fetchall()
        runs: List[Dict[str, Any]] = []
        for row in rows:
            runs.append(
                {
                    "id": row[0],
                    "test_case_id": row[1],
                    "status": row[2],
                    "started_at": row[3],
                    "ended_at": row[4],
                    "error_message": row[5],
                }
            )
        return runs

    def get_run_steps(self, test_run_id: int) -> List[Dict[str, Any]]:
        """Return step results for a specific test run."""
        cursor = self.conn.cursor()
        cursor.execute(
            "SELECT step_index, status, message, started_at, ended_at FROM run_steps WHERE test_run_id = ?",
            (test_run_id,),
        )
        rows = cursor.fetchall()
        results: List[Dict[str, Any]] = []
        for row in rows:
            results.append(
                {
                    "step_index": row[0],
                    "status": row[1],
                    "message": row[2],
                    "started_at": row[3],
                    "ended_at": row[4],
                }
            )
        return results

    # Version management
    def record_version(self, user_story: str, test_set: str, version: int, source: str, file_name: Optional[str], comments: Optional[str]) -> None:
        """Record a new version entry for a test case."""
        cursor = self.conn.cursor()
        cursor.execute(
            """
            INSERT INTO versions (user_story, test_set, version, source, file_name, comments, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (user_story, test_set, version, source, file_name, comments, self._now()),
        )
        self.conn.commit()

    def get_next_version(self, user_story: str, test_set: str) -> int:
        """Determine the next version number for a given user story and test set."""
        cursor = self.conn.cursor()
        cursor.execute(
            "SELECT MAX(version) FROM versions WHERE user_story = ? AND test_set = ?",
            (user_story, test_set),
        )
        row = cursor.fetchone()
        return (row[0] + 1) if row and row[0] is not None else 1

    def get_version_history(self, user_story: str, test_set: str) -> List[Dict[str, Any]]:
        """Return all recorded versions for a user story and test set."""
        cursor = self.conn.cursor()
        cursor.execute(
            """
            SELECT version, source, file_name, comments, created_at
            FROM versions
            WHERE user_story = ? AND test_set = ?
            ORDER BY version ASC
            """,
            (user_story, test_set),
        )
        rows = cursor.fetchall()
        history: List[Dict[str, Any]] = []
        for row in rows:
            history.append(
                {
                    "version": row[0],
                    "source": row[1],
                    "file_name": row[2],
                    "comments": row[3],
                    "created_at": row[4],
                }
            )
        return history


__all__ = ["Database"]