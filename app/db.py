"""Database helpers for the SQL-agent starter.

This is plumbing you can rely on — you should NOT need to change it.

What you get:
  * init_db()      -> seeds shop.db from seed.sql on first run
  * get_schema()   -> the CREATE TABLE statements as a string (feed this to your LLM)
  * run_query(sql) -> executes a read-only SELECT and returns (columns, rows)

Safety: run_query opens the database in read-only mode AND rejects anything
that isn't a single SELECT/WITH statement. The model's output is untrusted
input — keep it that way.
"""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

# Interviewers can switch datasets without touching any code, e.g.:
#   DB_FILE=shop_hard.db SEED_FILE=seed_hard.sql uv run uvicorn app.main:app
# Defaults reproduce the original baseline exactly.
DB_PATH = BASE_DIR / os.environ.get("DB_FILE", "shop.db")
SEED_PATH = BASE_DIR / os.environ.get("SEED_FILE", "seed.sql")


class UnsafeQueryError(ValueError):
    """Raised when a query is not a single read-only SELECT statement."""


def init_db() -> None:
    """Create and seed shop.db from seed.sql if it doesn't already exist."""
    if DB_PATH.exists():
        return
    if not SEED_PATH.exists():
        raise FileNotFoundError(f"Cannot seed database: {SEED_PATH} not found")
    conn = sqlite3.connect(DB_PATH)
    try:
        conn.executescript(SEED_PATH.read_text())
        conn.commit()
    finally:
        conn.close()


def get_schema() -> str:
    """Return the CREATE TABLE statements for all user tables.

    This is what you want to put in your prompt so the model knows the
    tables, columns, and types it can query.
    """
    conn = _connect_readonly()
    try:
        rows = conn.execute(
            "SELECT sql FROM sqlite_master "
            "WHERE type = 'table' AND name NOT LIKE 'sqlite_%' "
            "ORDER BY name"
        ).fetchall()
    finally:
        conn.close()
    return "\n\n".join(r[0] for r in rows if r[0])


def run_query(sql: str) -> tuple[list[str], list[list]]:
    """Execute a single read-only SELECT and return (columns, rows).

    Raises:
        UnsafeQueryError: if the SQL isn't a single SELECT/WITH statement.
        sqlite3.Error:    if the SQL is invalid or fails to execute. Catch
                          this in your agent loop and feed the message back
                          to the model so it can repair the query.
    """
    _assert_read_only(sql)
    conn = _connect_readonly()
    try:
        cursor = conn.execute(sql)
        columns = [d[0] for d in cursor.description] if cursor.description else []
        rows = [list(r) for r in cursor.fetchall()]
        return columns, rows
    finally:
        conn.close()


# --- internals -------------------------------------------------------------

def _connect_readonly() -> sqlite3.Connection:
    # mode=ro means the OS-level connection physically cannot write.
    uri = f"file:{DB_PATH}?mode=ro"
    return sqlite3.connect(uri, uri=True)


def _assert_read_only(sql: str) -> None:
    stripped = sql.strip().rstrip(";").strip()
    if not stripped:
        raise UnsafeQueryError("Empty query.")
    # Reject multiple statements (defense in depth alongside mode=ro).
    if ";" in stripped:
        raise UnsafeQueryError("Only a single statement is allowed.")
    first_word = stripped.split(None, 1)[0].lower()
    if first_word not in ("select", "with"):
        raise UnsafeQueryError(
            f"Only SELECT queries are allowed (got '{first_word.upper()}')."
        )
