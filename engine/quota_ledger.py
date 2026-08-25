"""Module for managing and tracking adapter usage quotas using a SQLite database."""

import sqlite3
import argparse
import sys
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Generator, Optional

DB_PATH = "quota_ledger.db"


class QuotaLedgerError(Exception):
    """Base exception for quota ledger errors."""
    pass


class QuotaExceededError(QuotaLedgerError):
    """Raised when an adapter's quota is exceeded."""
    pass


class QuotaAdapterNotFoundError(QuotaLedgerError):
    """Raised when an adapter is not found in the ledger."""
    pass


@contextmanager
def get_db_connection(db_path: Optional[str] = None) -> Generator[sqlite3.Connection, None, None]:
    """Context manager for database connections with automatic commit/rollback."""
    conn = sqlite3.connect(db_path or DB_PATH)
    try:
        yield conn
        conn.commit()
    except sqlite3.Error as e:
        conn.rollback()
        raise QuotaLedgerError(f"Database error: {e}") from e
    finally:
        conn.close()


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
        if last_reset != today:
            used = 0

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
    parser.add_argument("--init", action="store_true")
    parser.add_argument("--check", nargs=2, metavar=('ID', 'TOKENS'))
    parser.add_argument("--record", nargs=2, metavar=('ID', 'TOKENS'))
    args = parser.parse_args()

    if args.init:
        init_db()
        return 0
    elif args.check:
        if check_quota(args.check[0], int(args.check[1])):
            return 0
        else:
            return 1
    elif args.record:
        record_usage(args.record[0], int(args.record[1]))
        return 0
    else:
        return 2


if __name__ == "__main__":
    sys.exit(main())