"""
Versioning Utilities
--------------------

The versioning module centralises logic for managing test case
versions.  Each combination of (user story, test set) is versioned
independently.  When a test case is updated the version number
increments; older versions remain in the history and can be inspected
or rolled back via the dashboard.

This module is intentionally lightweight and delegates all database
interactions to :class:`utils.db_utils.Database`.  Higher level
components are expected to pass an instance of that class when
instantiating :class:`VersionManager`.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from ..utils.db_utils import Database


class VersionManager:
    """Manage test case version numbers and history."""

    def __init__(self, db: Database) -> None:
        self.db = db

    def get_next_version(self, user_story: str, test_set: str) -> int:
        """Return the next version number for a user story and test set."""
        return self.db.get_next_version(user_story, test_set)

    def record_version(self, user_story: str, test_set: str, source: str, file_name: Optional[str], comments: Optional[str]) -> int:
        """Record a new version entry and return the assigned version number.

        Before inserting a new version, this method checks whether a
        previous version with identical metadata (user story, test set and
        file name) already exists.  If a duplicate is found the version
        number is not incremented; instead a new record is inserted with
        a comment indicating duplication.  Composite keys (user_story,
        test_set) ensure that duplicate user stories are preserved for
        auditing but flagged appropriately.

        :param user_story: The user story name.
        :param test_set: The test set name (e.g. Positive, Negative).
        :param source: The upload source (e.g. manual, generated).
        :param file_name: Optional file name associated with the upload.
        :param comments: Optional user comment.
        :returns: The newly assigned version number or the existing one if duplicate.
        """
        # Fetch history and determine if this upload is a duplicate
        history = self.db.get_version_history(user_story, test_set)
        for record in history:
            if record.get("file_name") == file_name:
                # Duplicate detected; record a new entry but reuse version number
                dup_version = record.get("version")
                self.db.record_version(
                    user_story,
                    test_set,
                    dup_version,
                    source,
                    file_name,
                    (comments or "") + " (duplicate)"
                )
                return dup_version
        # Not duplicate – assign next version
        new_version = self.get_next_version(user_story, test_set)
        self.db.record_version(user_story, test_set, new_version, source, file_name, comments)
        return new_version

    def get_history(self, user_story: str, test_set: str) -> List[Dict[str, Any]]:
        """Return the version history for a user story and test set."""
        return self.db.get_version_history(user_story, test_set)


__all__ = ["VersionManager"]