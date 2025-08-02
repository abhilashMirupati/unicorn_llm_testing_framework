"""
Natural Language to SQL Translator
---------------------------------

This module provides a very simple rule‑based translator that converts
plain‑English instructions into SQL statements.  It is not intended to be
a full natural language interface but demonstrates how LLMs or rules can
drive SQL operations.  Each translation returns both a SQL statement and
an optional assertion function to validate results.
"""

import re
from dataclasses import dataclass
from typing import Callable, Optional, Tuple, Any


@dataclass
class SQLTranslation:
    sql: str
    assertion: Optional[Callable[[Any], None]] = None


def english_to_sql(command: str) -> SQLTranslation:
    """Translate a simple English command into a SQL statement and assertion.

    Supported forms:

    * "insert user John Doe" → `INSERT INTO users (name) VALUES ('John Doe');`
    * "verify exists user John Doe" → `SELECT COUNT(*) FROM users WHERE name='John Doe';`
    * "delete user John Doe" → `DELETE FROM users WHERE name='John Doe';`

    Additional verbs and tables can be added by extending the rules below.
    """
    cmd = command.strip().lower()
    # Insert user
    m = re.match(r"insert user (.+)", cmd)
    if m:
        name = m.group(1).title()
        sql = f"INSERT INTO users (name) VALUES ('{name}');"

        def assertion(cursor):
            cursor.execute("SELECT COUNT(*) FROM users WHERE name=?", (name,))
            count = cursor.fetchone()[0]
            assert count > 0, f"User '{name}' was not inserted"

        return SQLTranslation(sql, assertion)

    # Verify exists user
    m = re.match(r"verify exists user (.+)", cmd)
    if m:
        name = m.group(1).title()
        sql = f"SELECT COUNT(*) FROM users WHERE name='{name}';"

        def assertion(cursor):
            row = cursor.fetchone()
            count = row[0] if row else 0
            assert count > 0, f"User '{name}' does not exist"

        return SQLTranslation(sql, assertion)

    # Delete user
    m = re.match(r"delete user (.+)", cmd)
    if m:
        name = m.group(1).title()
        sql = f"DELETE FROM users WHERE name='{name}';"

        def assertion(cursor):
            cursor.execute("SELECT COUNT(*) FROM users WHERE name=?", (name,))
            count = cursor.fetchone()[0]
            assert count == 0, f"User '{name}' was not deleted"

        return SQLTranslation(sql, assertion)

    # Fallback: treat command as raw SQL
    return SQLTranslation(command, None)


__all__ = ["english_to_sql", "SQLTranslation"]