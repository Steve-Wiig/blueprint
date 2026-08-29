import sqlite3
import argparse
import sys
import os
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Generator, Optional


def _get_default_db_path() -> str:
    """Get default database path from environment variable or fallback."""
    return os.environ.get("QUOTA_LEDGER_DB_PATH", "quota_ledger.db")


def _get_pool_enabled() -> bool:
    """Check if connection pooling is enabled via environment variable."""
    return os.environ.get("QUOTA_LEDGER_POOL_CONNECTIONS", "false").lower() in ("1", "true", "yes")


DB_PATH = _get_default_db_path()
_POOL_ENABLED = _get_pool_enabled()
_thread_local = threading.local()


class QuotaLedgerError(Exception):
    """Base exception for quota ledger errors."""
    pass


class QuotaExceededError(QuotaLedgerError):
    """Raised when an adapter's quota is exceeded."""
    pass


class QuotaAdapterNotFoundError(QuotaLedgerError):
    """Raised when an adapter is not found in the ledger."""
    pass


def _get_pooled_connection(db_path: str) -> sqlite3.Connection:
    """Get or create a thread-local pooled connection."""
    if not hasattr(_thread_local, 'conn') or _thread_local.conn is None:
        _thread_local.conn = sqlite3.connect(db_path, check_same_thread=False)
        _thread_local.conn.execute("PRAGMA foreign_keys = ON")
    elif _thread_local.db_path != db_path:
        _thread_local.conn.close()
        _thread_local.conn = sqlite3.connect(db_path, check_same_thread=False)
        _thread_local.conn.execute("PRAGMA foreign_keys = ON")
    _thread_local.db_path = db_path
    return _thread_local.conn


def _release_pooled_connection() -> None:
    """Close and clear the thread-local pooled connection."""
    if hasattr(_thread_local, 'conn') and _thread_local.conn is not None:
        _thread_local.conn.close()
        _thread_local.conn = None
        _thread_local.db_path = None


@contextmanager
def get_db_connection(db_path: Optional[str] = None) -> Generator[sqlite3.Connection, None, None]:
    """Context manager for database connections with automatic commit/rollback.

    If connection pooling is enabled (QUOTA_LEDGER_POOL_CONNECTIONS=1), reuses a
    thread-local connection instead of creating a new one each time.
    """
    resolved_path = db_path or DB_PATH

    if _POOL_ENABLED:
        conn = _get_pooled_connection(resolved_path)
        try:
            yield conn
            conn.commit()
        except sqlite3.Error as e:
            conn.rollback()
            raise QuotaLedgerError(f"Database error: {e}") from e
    else:
        conn = sqlite3.connect(resolved_path)
        try:
            yield conn
            conn.commit()
        except sqlite3.Error as e:
            conn.rollback()
            raise QuotaLedgerError(f"Database error: {e}") from e
        finally:
            conn.close()


def close_connection_pool() -> None:
    """Close the thread-local pooled connection if pooling is enabled.

    Call this at thread shutdown or application exit to clean up resources.
    """
    if _POOL_ENABLED:
        _release_pooled_connection()


def init_db(db_path: Optional[str] = None) -> None:
    """Initializes the quota ledger database and creates the table if it does not exist."""
    try:
        with get_db_connection(db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS quota_ledger (
                    adapter_id TEXT PRIMARY KEY,
                    daily_limit INTEGER NOT NULL CHECK (daily_limit > 0),
                    job_limit INTEGER NOT NULL CHECK (job_limit > 0),
                    tokens_used_today INTEGER DEFAULT 0,
                    last_reset_date TEXT
                )
            ''')
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS quota_audit (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    adapter_id TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    tokens_delta INTEGER NOT NULL,
                    operation TEXT NOT NULL,
                    previous_total INTEGER NOT NULL,
                    new_total INTEGER NOT NULL
                )
            ''')
            cursor.execute('''
                CREATE INDEX IF NOT EXISTS idx_quota_audit_adapter_id ON quota_audit(adapter_id)
            ''')
            cursor.execute('''
                CREATE INDEX IF NOT EXISTS idx_quota_audit_timestamp ON quota_audit(timestamp)
            ''')
    except sqlite3.Error as e:
        raise QuotaLedgerError(f"Database initialization failed: {e}") from e


def _reset_daily_if_needed(used: int, last_reset: str, today: str) -> int:
    """Reset daily usage to zero if the reset date differs from today."""
    if last_reset != today:
        return 0
    return used


def check_quota(adapter_id: str, estimated_tokens: int, db_path: Optional[str] = None) -> bool:
    """Checks if an adapter has sufficient quota for a given token usage.

    Args:
        adapter_id: The unique identifier for the adapter.
        estimated_tokens: The number of tokens to be used.
        db_path: Optional database path for testing.

    Returns:
        True if the usage is within limits, False otherwise.
    """
    try:
        with get_db_connection(db_path) as conn:
            cursor = conn.cursor()
            today = datetime.now(timezone.utc).strftime('%Y-%m-%d')

            cursor.execute(
                "SELECT daily_limit, job_limit, tokens_used_today, last_reset_date FROM quota_ledger WHERE adapter_id = ?",
                (adapter_id,)
            )
            row = cursor.fetchone()

        if not row:
            return False

        daily_limit, job_limit, used, last_reset = row
        used = _reset_daily_if_needed(used, last_reset, today)

        if (used + estimated_tokens) > daily_limit or estimated_tokens > job_limit:
            return False
        return True
    except sqlite3.Error as e:
        raise QuotaLedgerError(f"Database error during quota check: {e}") from e

def record_usage(adapter_id: str, tokens_used: int, db_path: Optional[str] = None) -> None:
    """Records token usage for a specific adapter in the database.

    Args:
        adapter_id: The unique identifier for the adapter.
        tokens_used: The number of tokens to record.
        db_path: Optional database path for testing.
    """
    try:
        with get_db_connection(db_path) as conn:
            cursor = conn.cursor()
            today = datetime.now(timezone.utc).strftime('%Y-%m-%d')
            timestamp = datetime.now(timezone.utc).isoformat()

            cursor.execute(
                "SELECT tokens_used_today, last_reset_date FROM quota_ledger WHERE adapter_id = ?",
                (adapter_id,)
            )
            row = cursor.fetchone()

            if row:
                used, last_reset = row
                previous_total = used if last_reset == today else 0
                new_used = previous_total + tokens_used
                cursor.execute(
                    "UPDATE quota_ledger SET tokens_used_today = ?, last_reset_date = ? WHERE adapter_id = ?",
                    (new_used, today, adapter_id)
                )
                cursor.execute(
                    "INSERT INTO quota_audit (adapter_id, timestamp, tokens_delta, operation, previous_total, new_total) VALUES (?, ?, ?, ?, ?, ?)",
                    (adapter_id, timestamp, tokens_used, 'usage', previous_total, new_used)
                )
    except sqlite3.Error as e:
        raise QuotaLedgerError(f"Database error during usage recording: {e}") from e


def main() -> int:
    """Parses command line arguments and executes the requested quota management operation.

    Returns:
        int: Process exit code.
            0 = success (init completed / check passed / usage recorded)
            1 = check failed (quota exceeded or adapter not found)
            2 = no operation specified (usage error)
    """
    parser = argparse.ArgumentParser(description="SLM Quota Ledger Manager")
    parser.add_argument("--db-path", default=DB_PATH, help="Path to SQLite database (default: quota_ledger.db or QUOTA_LEDGER_DB_PATH env var)")
    parser.add_argument("--init", action="store_true")
    parser.add_argument("--check", nargs=2, metavar=('ID', 'TOKENS'))
    parser.add_argument("--record", nargs=2, metavar=('ID', 'TOKENS'))
    args = parser.parse_args()

    db_path = args.db_path

    if args.init:
        init_db(db_path)
        return 0
    elif args.check:
        if check_quota(args.check[0], int(args.check[1]), db_path):
            return 0
        else:
            return 1
    elif args.record:
        record_usage(args.record[0], int(args.record[1]), db_path)
        return 0
    else:
        return 2


if __name__ == "__main__":
    try:
        sys.exit(main())
    finally:
        close_connection_pool()