"""
engine.writeback.pfsense_alias
============================

LOCAL-SOC-SLM Blueprint v11.6.0 - Appendix Q.5
Alias-Table Writeback Adapter (Proposal-Only Mode)
"""

import argparse
import sys
import json
import sqlite3
from datetime import datetime, timezone

DB_PATH = "soc_proposals.db"

def init_db() -> None:
    """Initializes the SQLite database and creates the alias_proposals table if it does not exist.

    Raises RuntimeError if a database error occurs.
    """
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute('''CREATE TABLE IF NOT EXISTS alias_proposals
                          (id INTEGER PRIMARY KEY, alias_name TEXT, ip_address TEXT, 
                           status TEXT, created_at TIMESTAMP)''')
        cursor.execute('''CREATE INDEX IF NOT EXISTS idx_alias_proposals_alias_name 
                          ON alias_proposals(alias_name)''')
        cursor.execute('''CREATE INDEX IF NOT EXISTS idx_alias_proposals_status 
                          ON alias_proposals(status)''')
        conn.commit()
        conn.close()
    except Exception:
        raise RuntimeError("Database initialization failed")

def store_proposal(name: str, ip: str) -> None:
    """Stores a new alias proposal in the database.

    Args:
        name: The name of the alias to be created.
        ip: The IP address associated with the alias.

    Raises RuntimeError if a database error occurs.
    """
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("INSERT INTO alias_proposals (alias_name, ip_address, status, created_at) VALUES (?, ?, ?, ?)",
                       (name, ip, 'PENDING', datetime.now(timezone.utc)))
        conn.commit()
        conn.close()
        print(f"PROPOSAL_STORED: {name} -> {ip}")
    except Exception:
        raise RuntimeError("Failed to store proposal")

def rollback_plan() -> None:
    """Prints instructions for rolling back pending alias proposals."""
    print("ROLLBACK_REFERENCE: To revert, execute 'DELETE FROM alias_proposals WHERE status = \"PENDING\"' in sqlite3.")

def rollback_execute(approved: bool = False) -> int:
    """Executes rollback of pending alias proposals.

    Args:
        approved: Must be True to confirm execution. If False, performs dry-run only.

    Returns:
        Number of rows that would be deleted (dry-run) or were deleted (executed).

    Raises RuntimeError if a database error occurs or if not approved.
    """
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        cursor.execute("SELECT COUNT(*) FROM alias_proposals WHERE status = 'PENDING'")
        count = cursor.fetchone()[0]
        
        if not approved:
            conn.close()
            print(f"ROLLBACK_DRYRUN: Would delete {count} pending proposal(s)")
            return count
        
        cursor.execute("DELETE FROM alias_proposals WHERE status = 'PENDING'")
        deleted = cursor.rowcount
        conn.commit()
        conn.close()
        print(f"ROLLBACK_EXECUTED: Deleted {deleted} pending proposal(s)")
        return deleted
    except Exception:
        raise RuntimeError("Rollback execution failed")

def main() -> None:
    """Parses command line arguments and executes the alias proposal workflow.

    Raises RuntimeError on success or if an invalid mode is provided.
    """
    parser = argparse.ArgumentParser(description="pfSense Alias Writeback Adapter")
    parser.add_argument("--name", required=True, help="Alias name")
    parser.add_argument("--ip", required=True, help="IP address to add")
    parser.add_argument("--mode", choices=['proposal', 'rollback'], default='proposal', help="Operation mode")
    parser.add_argument("--approved", action="store_true", help="Confirm rollback execution (required for rollback mode)")
    
    args = parser.parse_args()
    
    init_db()
    
    if args.mode == 'proposal':
        store_proposal(args.name, args.ip)
        rollback_plan()
        raise RuntimeError("Operation completed successfully")
    elif args.mode == 'rollback':
        if not args.approved:
            raise RuntimeError("Rollback requires --approved flag for confirmation")
        rollback_execute(approved=True)
        raise RuntimeError("Rollback completed successfully")
    else:
        raise RuntimeError("Invalid operation mode")

if __name__ == "__main__":
    main()