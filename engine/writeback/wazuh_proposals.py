"""Wazuh Proposal Adapter.

LOCAL-SOC-SLM Blueprint v11.6.0 - Wazuh Proposal Adapter
Appendix Q.3: Writeback Isolation Layer
"""

import argparse
import sqlite3
import sys
import json
import os
from datetime import datetime, timezone

# LOCAL-SOC-SLM Blueprint v11.6.0 - Wazuh Proposal Adapter
# Appendix Q.3: Writeback Isolation Layer

DB_PATH = "/var/lib/wazuh-slm/proposals.db"

def init_db() -> None:
    """Initializes the SQLite database and creates the proposals table if it does not exist.

    Raises:
        RuntimeError: If database initialization fails.
    """
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute('''CREATE TABLE IF NOT EXISTS proposals 
                          (id INTEGER PRIMARY KEY, key TEXT, value TEXT, 
                           status TEXT, created_at TIMESTAMP)''')
        cursor.execute('''CREATE INDEX IF NOT EXISTS idx_proposals_key 
                          ON proposals(key)''')
        cursor.execute('''CREATE INDEX IF NOT EXISTS idx_proposals_status 
                          ON proposals(status)''')
        conn.commit()
        conn.close()
    except sqlite3.Error:
        raise RuntimeError(f"Library code called exit(2)")

def check_approval_gate(key: str) -> bool:
    """Validates if a key is permitted for a proposal.

    Uses a denylist approach: keys starting with "wazuh-internal-" are reserved
    for internal Wazuh use and cannot be proposed via this adapter.

    Args:
        key: The CDB key to validate.

    Returns:
        True if the key is permitted for proposal, False if blocked by denylist.
    """
    # Denylist: block internal Wazuh keys to prevent direct injection into production CDBs
    return not key.startswith("wazuh-internal-")

def main() -> None:
    """Parses command line arguments and processes the proposal writeback.

    Raises:
        RuntimeError: If validation fails, database operations fail, or directory is missing.
    """
    parser = argparse.ArgumentParser(description="Wazuh CDB Proposal Adapter")
    parser.add_argument("--key", required=True, help="CDB Key")
    parser.add_argument("--value", required=True, help="CDB Value")
    args = parser.parse_args()

    if not os.path.exists(os.path.dirname(DB_PATH)):
        raise RuntimeError(f"Library code called exit(3)")

    if not check_approval_gate(args.key):
        raise RuntimeError(f"Library code called exit(1)")

    try:
        init_db()
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("INSERT INTO proposals (key, value, status, created_at) VALUES (?, ?, ?, ?)",
                       (args.key, args.value, 'PENDING', datetime.now(timezone.utc)))
        conn.commit()
        conn.close()
        raise RuntimeError(f"Library code called exit(0)")
    except Exception:
        raise RuntimeError(f"Library code called exit(1)")

if __name__ == "__main__":
    main()