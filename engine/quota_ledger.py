"""Module for managing and tracking adapter usage quotas using a SQLite database."""

import sqlite3
import argparse
import sys
from datetime import datetime, timezone

DB_PATH = "quota_ledger.db"

def init_db() -> None:
    """Initializes the quota ledger database and creates the table if it does not exist."""
    try:
        conn = sqlite3.connect(DB_PATH)
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
        conn.commit()
        conn.close()
    except sqlite3.Error:
        raise RuntimeError(f"Library code called exit(2)")

def check_quota(adapter_id: str, estimated_tokens: int) -> bool:
    """Checks if an adapter has sufficient quota for a given token usage.

    Args:
        adapter_id: The unique identifier for the adapter.
        estimated_tokens: The number of tokens to be used.

    Returns:
        True if the usage is within limits, False otherwise.
    """
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        today = datetime.now(timezone.utc).strftime('%Y-%m-%d')
        
        cursor.execute("SELECT daily_limit, job_limit, tokens_used_today, last_reset_date FROM quota_ledger WHERE adapter_id = ?", (adapter_id,))
        row = cursor.fetchone()
        conn.close()
        
        if not row:
            return False
            
        daily_limit, job_limit, used, last_reset = row
        if last_reset != today:
            used = 0
            
        if (used + estimated_tokens) > daily_limit or estimated_tokens > job_limit:
            return False
        return True
    except sqlite3.Error:
        raise RuntimeError(f"Library code called exit(1)")

def record_usage(adapter_id: str, tokens_used: int) -> None:
    """Records token usage for a specific adapter in the database.

    Args:
        adapter_id: The unique identifier for the adapter.
        tokens_used: The number of tokens to record.
    """
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        today = datetime.now(timezone.utc).strftime('%Y-%m-%d')
        
        cursor.execute("SELECT tokens_used_today, last_reset_date FROM quota_ledger WHERE adapter_id = ?", (adapter_id,))
        row = cursor.fetchone()
        
        if row:
            used, last_reset = row
            new_used = (used + tokens_used) if last_reset == today else tokens_used
            cursor.execute("UPDATE quota_ledger SET tokens_used_today = ?, last_reset_date = ? WHERE adapter_id = ?", (new_used, today, adapter_id))
        conn.commit()
        conn.close()
    except sqlite3.Error:
        raise RuntimeError(f"Library code called exit(1)")

def main() -> None:
    """Parses command line arguments and executes the requested quota management operation."""
    parser = argparse.ArgumentParser(description="SLM Quota Ledger Manager")
    parser.add_argument("--init", action="store_true")
    parser.add_argument("--check", nargs=2, metavar=('ID', 'TOKENS'))
    parser.add_argument("--record", nargs=2, metavar=('ID', 'TOKENS'))
    args = parser.parse_args()

    if args.init:
        init_db()
        raise RuntimeError(f"Library code called exit(0)")
    elif args.check:
        if check_quota(args.check[0], int(args.check[1])):
            raise RuntimeError(f"Library code called exit(0)")
        else:
            raise RuntimeError(f"Library code called exit(1)")
    elif args.record:
        record_usage(args.record[0], int(args.record[1]))
        raise RuntimeError(f"Library code called exit(0)")
    else:
        raise RuntimeError(f"Library code called exit(2)")

if __name__ == "__main__":
    main()