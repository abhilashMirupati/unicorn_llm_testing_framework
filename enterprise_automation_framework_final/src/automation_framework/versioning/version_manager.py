"""
Version Manager
---------------

This module manages versioned test sets.  Each BRD or user story is
stored as a separate entity with an arbitrary number of versions.  A
version consists of a list of test cases and metadata (author,
timestamp, user story identifier).  When a new version is added, the
manager compares it against the previous version for the same user
story and marks each test case as added, removed or unchanged.  Even
if the new version is highly similar (>80 %) to the previous one, it
is always saved and the similarity percentage is recorded.  Test cases
are never lost and users can later merge or compare versions.
"""

from __future__ import annotations

import datetime as _dt
import json
import sqlite3
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from ..utils.logger import get_logger


class VersionManager:
    """Manage versioned test sets using a SQLite database."""

    def __init__(self, config) -> None:
        self.config = config
        self.logger = get_logger(self.__class__.__name__)
        db_url = config.get("database.url", "sqlite:///./test_sets.db")
        if db_url.startswith("sqlite:///"):
            db_path = db_url[len("sqlite:///"):]
        else:
            db_path = db_url
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        # When using SQLite across threads (e.g. FastAPI async endpoints or background
        # thread pools), the default connection will raise errors if used
        # outside of the thread that created it.  Setting
        # check_same_thread=False allows the connection to be shared safely
        # across threads.  Note that SQLite connections are not inherently
        # thread-safe, so higher-level code must ensure that individual
        # operations do not overlap (e.g. by running database actions
        # sequentially in the event loop or by using a thread pool).  For our
        # version manager the usage pattern is simple and we avoid concurrent
        # writes within the same test run, so this flag is sufficient.
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self.cursor = self.conn.cursor()
        self._ensure_schema()

    def _ensure_schema(self) -> None:
        self.cursor.execute(
            """CREATE TABLE IF NOT EXISTS test_set_versions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_story TEXT NOT NULL,
                version_number INTEGER NOT NULL,
                author TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                similarity REAL NOT NULL,
                test_cases_json TEXT NOT NULL
            )"""
        )
        self.conn.commit()

    def _get_latest_version_info(self, user_story: str) -> Optional[Tuple[int, int, List[Dict[str, Any]], float]]:
        """Return (id, version_number, cases, similarity) for the most recent version of a user story."""
        self.cursor.execute(
            "SELECT id, version_number, test_cases_json, similarity FROM test_set_versions WHERE user_story=? ORDER BY version_number DESC LIMIT 1",
            (user_story,),
        )
        row = self.cursor.fetchone()
        if row:
            version_id, version_number, cases_json, similarity = row
            cases = json.loads(cases_json)
            return version_id, version_number, cases, similarity
        return None

    def _compute_similarity(self, old_cases: List[Dict[str, Any]], new_cases: List[Dict[str, Any]]) -> float:
        """Compute a similarity ratio between two test case lists.

        The comparison method is controlled via configuration.  By
        default a semantic similarity is computed using TF‑IDF
        embeddings and cosine similarity.  If scikit‑learn is not
        available or the method is set to "sequence", difflib's
        SequenceMatcher ratio is used as a fallback.
        """
        method = str(self.config.get("versioning.method", "sequence")).lower()
        try:
            if method == "embedding":
                # Build TF‑IDF vectors
                from sklearn.feature_extraction.text import TfidfVectorizer  # type: ignore
                from sklearn.metrics.pairwise import cosine_similarity  # type: ignore
                old_texts = [json.dumps(tc, sort_keys=True) for tc in old_cases]
                new_texts = [json.dumps(tc, sort_keys=True) for tc in new_cases]
                vectorizer = TfidfVectorizer().fit(old_texts + new_texts)
                old_vec = vectorizer.transform(["\n".join(old_texts)])
                new_vec = vectorizer.transform(["\n".join(new_texts)])
                sim = cosine_similarity(old_vec, new_vec)[0][0]
                return float(sim)
        except Exception as exc:
            self.logger.warning("Embedding similarity failed (%s); falling back to SequenceMatcher", exc)
        # Fallback to SequenceMatcher
        old_text = "\n".join(json.dumps(tc, sort_keys=True) for tc in old_cases)
        new_text = "\n".join(json.dumps(tc, sort_keys=True) for tc in new_cases)
        return SequenceMatcher(None, old_text, new_text).ratio()

    def add_version(
        self, user_story: str, test_cases: List[Dict[str, Any]], author: str = "unknown"
    ) -> Dict[str, Any]:
        """Add a new version for a user story and return metadata including differences."""
        latest = self._get_latest_version_info(user_story)
        version_number = (latest[1] + 1) if latest else 1
        similarity = 0.0
        diff: Dict[str, List[Dict[str, Any]]] = {"added": [], "removed": [], "unchanged": []}
        if latest:
            _, _, old_cases, _ = latest
            similarity = self._compute_similarity(old_cases, test_cases)
            # Determine case differences by matching identifiers
            old_map = {c.get("identifier"): c for c in old_cases}
            new_map = {c.get("identifier"): c for c in test_cases}
            for key in new_map:
                if key in old_map:
                    diff["unchanged"].append(new_map[key])
                else:
                    diff["added"].append(new_map[key])
            for key in old_map:
                if key not in new_map:
                    diff["removed"].append(old_map[key])
        else:
            diff["added"] = test_cases

        # Persist the new version
        timestamp = _dt.datetime.now().isoformat()
        self.cursor.execute(
            "INSERT INTO test_set_versions (user_story, version_number, author, timestamp, similarity, test_cases_json) VALUES (?,?,?,?,?,?)",
            (
                user_story,
                version_number,
                author,
                timestamp,
                similarity,
                json.dumps(test_cases, ensure_ascii=False),
            ),
        )
        self.conn.commit()
        version_id = self.cursor.lastrowid
        self.logger.info(
            "Added version %s for story '%s' (similarity=%.2f)",
            version_number,
            user_story,
            similarity,
        )
        # Warn if the new version is highly similar
        threshold = float(self.config.get("versioning.similarity_threshold", 0.8))
        if latest and similarity >= threshold:
            self.logger.warning(
                "New version of '%s' is %.0f%% similar to the previous one (threshold %.0f%%)",
                user_story,
                similarity * 100,
                threshold * 100,
            )
        return {
            "version_id": version_id,
            "version_number": version_number,
            "similarity": similarity,
            "diff": diff,
        }

    def list_versions(self, user_story: str) -> List[Dict[str, Any]]:
        """List all versions for a user story with metadata."""
        self.cursor.execute(
            "SELECT id, version_number, author, timestamp, similarity FROM test_set_versions WHERE user_story=? ORDER BY version_number",
            (user_story,),
        )
        rows = self.cursor.fetchall()
        return [
            {
                "id": row[0],
                "version_number": row[1],
                "author": row[2],
                "timestamp": row[3],
                "similarity": row[4],
            }
            for row in rows
        ]

    def get_test_cases(self, version_id: int) -> List[Dict[str, Any]]:
        """Retrieve the list of test cases for a given version id."""
        self.cursor.execute(
            "SELECT test_cases_json FROM test_set_versions WHERE id=?",
            (version_id,),
        )
        row = self.cursor.fetchone()
        if not row:
            raise ValueError(f"Version {version_id} not found")
        cases_json = row[0]
        return json.loads(cases_json)

    def compare_versions(self, version_id_a: int, version_id_b: int) -> Dict[str, List[Dict[str, Any]]]:
        """Compute a diff between two versions and return added/removed/unchanged test cases."""
        cases_a = self.get_test_cases(version_id_a)
        cases_b = self.get_test_cases(version_id_b)
        diff = {"added": [], "removed": [], "unchanged": []}
        map_a = {c.get("identifier"): c for c in cases_a}
        map_b = {c.get("identifier"): c for c in cases_b}
        for key in map_b:
            if key in map_a:
                diff["unchanged"].append(map_b[key])
            else:
                diff["added"].append(map_b[key])
        for key in map_a:
            if key not in map_b:
                diff["removed"].append(map_a[key])
        return diff

    def close(self) -> None:
        self.conn.close()