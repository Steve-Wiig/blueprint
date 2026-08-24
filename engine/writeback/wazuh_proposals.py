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

DB_PATH = os.environ.get("WAZUH_PROPOSALS_DB", "/var/lib/wazuh-slm/proposals.db")

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
        
        # Audit log table for append-only trail (Section 30 compliance)
        cursor.execute('''CREATE TABLE IF NOT EXISTS audit_log
                          (id INTEGER PRIMARY KEY, proposal_id INTEGER, action TEXT,
                           actor TEXT, timestamp TIMESTAMP,
                           FOREIGN KEY(proposal_id) REFERENCES proposals(id))''')
        cursor.execute('''CREATE INDEX IF NOT EXISTS idx_audit_log_proposal_id
                          ON audit_log(proposal_id)''')
        cursor.execute('''CREATE INDEX IF NOT EXISTS idx_audit_log_timestamp
                          ON audit_log(timestamp)''')
        
        # Trigger on INSERT to proposals
        cursor.execute('''CREATE TRIGGER IF NOT EXISTS audit_proposals_insert
                          AFTER INSERT ON proposals
                          BEGIN
                              INSERT INTO audit_log (proposal_id, action, actor, timestamp)
                              VALUES (NEW.id, 'INSERT', 'wazuh-proposal-adapter', datetime('now'));
                          END;''')
        
        # Trigger on UPDATE to proposals
        cursor.execute('''CREATE TRIGGER IF NOT EXISTS audit_proposals_update
                          AFTER UPDATE ON proposals
                          BEGIN
                              INSERT INTO audit_log (proposal_id, action, actor, timestamp)
                              VALUES (NEW.id, 'UPDATE', 'wazuh-proposal-adapter', datetime('now'));
                          END;''')
        
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

def parse_args() -> argparse.Namespace:
    """Parses command line arguments.

    Returns:
        Parsed arguments namespace with key and value attributes.
    """
    parser = argparse.ArgumentParser(description="Wazuh CDB Proposal Adapter")
    parser.add_argument("--key", required=True, help="CDB Key")
    parser.add_argument("--value", required=True, help="CDB Value")
    return parser.parse_args()

def validate_proposal(key: str) -> None:
    """Validates the proposal key and environment.

    Args:
        key: The CDB key to validate.

    Raises:
        RuntimeError: If validation fails (denylist or missing directory).
    """
    if not os.path.exists(os.path.dirname(DB_PATH)):
        raise RuntimeError(f"Library code called exit(3)")

    if not check_approval_gate(key):
        raise RuntimeError(f"Library code called exit(1)")

def store_proposal(key: str, value: str) -> None:
    """Stores the proposal in the database.

    Args:
        key: The CDB key.
        value: The CDB value.

    Raises:
        RuntimeError: If database operations fail.
    """
    try:
        init_db()
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("INSERT INTO proposals (key, value, status, created_at) VALUES (?, ?, ?, ?)",
                       (key, value, 'PENDING', datetime.now(timezone.utc)))
        conn.commit()
        conn.close()
    except Exception:
        raise RuntimeError(f"Library code called exit(1)")

def main() -> None:
    """Orchestrates the proposal writeback process.

    Raises:
        RuntimeError: If validation fails, database operations fail, or directory is missing.
    """
    args = parse_args()
    validate_proposal(args.key)
    store_proposal(args.key, args.value)
    raise RuntimeError(f"Library code called exit(0)")

if __name__ == "__main__":
    main()