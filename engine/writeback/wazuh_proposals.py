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
from typing import NoReturn

# LOCAL-SOC-SLM Blueprint v11.6.0 - Wazuh Proposal Adapter
# Appendix Q.3: Writeback Isolation Layer

DB_PATH: str = os.environ.get("WAZUH_PROPOSALS_DB", "/var/lib/wazuh-slm/proposals.db")

_db_initialized: bool = False


class ProposalError(Exception):
    """Base exception for proposal adapter errors."""
    def __init__(self, message: str, exit_code: int):
        super().__init__(message)
        self.exit_code = exit_code


class ProposalRejectedError(ProposalError):
    """Raised when a proposal is rejected (denylist, validation)."""
    def __init__(self, message: str = "Proposal rejected"):
        super().__init__(message, 1)


class ProposalStorageError(ProposalError):
    """Raised when database/storage operations fail."""
    def __init__(self, message: str = "Storage operation failed"):
        super().__init__(message, 2)


class ProposalDirectoryError(ProposalError):
    """Raised when required directory is missing."""
    def __init__(self, message: str = "Required directory missing"):
        super().__init__(message, 3)


class ProposalSuccess(ProposalError):
    """Raised on successful proposal submission."""
    def __init__(self, message: str = "Proposal stored successfully"):
        super().__init__(message, 0)


def init_db() -> None:
    """Initializes the SQLite database and creates the proposals table if it does not exist.

    Raises:
        ProposalStorageError: If database initialization fails.
    """
    global _db_initialized
    if _db_initialized:
        return
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
                           old_status TEXT, new_status TEXT, changed_by TEXT,
                           changed_at TIMESTAMP,
                           FOREIGN KEY(proposal_id) REFERENCES proposals(id))''')
        cursor.execute('''CREATE INDEX IF NOT EXISTS idx_audit_log_proposal_id
                          ON audit_log(proposal_id)''')
        cursor.execute('''CREATE INDEX IF NOT EXISTS idx_audit_log_timestamp
                          ON audit_log(changed_at)''')
        
        # Trigger on INSERT to proposals
        cursor.execute('''CREATE TRIGGER IF NOT EXISTS audit_proposals_insert
                          AFTER INSERT ON proposals
                          BEGIN
                              INSERT INTO audit_log (proposal_id, action, old_status, new_status, changed_by, changed_at)
                              VALUES (NEW.id, 'INSERT', NULL, NEW.status, 'wazuh-proposal-adapter', datetime('now'));
                          END;''')
        
        # Trigger on UPDATE of status column in proposals
        cursor.execute('''CREATE TRIGGER IF NOT EXISTS audit_proposals_status_change
                          AFTER UPDATE OF status ON proposals
                          WHEN OLD.status != NEW.status
                          BEGIN
                              INSERT INTO audit_log (proposal_id, action, old_status, new_status, changed_by, changed_at)
                              VALUES (NEW.id, 'STATUS_CHANGE', OLD.status, NEW.status, 'wazuh-proposal-adapter', datetime('now'));
                          END;''')
        
        conn.commit()
        conn.close()
        _db_initialized = True
    except sqlite3.Error as e:
        raise ProposalStorageError(f"Database initialization failed: {e}")


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
        ProposalDirectoryError: If the database directory does not exist.
        ProposalRejectedError: If the key is blocked by denylist.
    """
    if not os.path.exists(os.path.dirname(DB_PATH)):
        raise ProposalDirectoryError(f"Database directory does not exist: {os.path.dirname(DB_PATH)}")

    if not check_approval_gate(key):
        raise ProposalRejectedError(f"Key '{key}' is reserved for internal Wazuh use")


def store_proposal(key: str, value: str) -> None:
    """Stores the proposal in the database.

    Args:
        key: The CDB key.
        value: The CDB value.

    Raises:
        ProposalStorageError: If database operations fail.
    """
    try:
        init_db()
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("INSERT INTO proposals (key, value, status, created_at) VALUES (?, ?, ?, ?)",
                       (key, value, 'PENDING', datetime.now(timezone.utc)))
        conn.commit()
        conn.close()
    except ProposalError:
        raise
    except Exception as e:
        raise ProposalStorageError(f"Failed to store proposal: {e}")


def main() -> NoReturn:
    """Orchestrates the proposal writeback process.

    Raises:
        ProposalError: On any failure or success (with appropriate exit_code).
    """
    args = parse_args()
    validate_proposal(args.key)
    store_proposal(args.key, args.value)
    raise ProposalSuccess("Proposal stored successfully")


if __name__ == "__main__":
    try:
        main()
    except ProposalError as e:
        print(str(e), file=sys.stderr)
        sys.exit(e.exit_code)