import argparse
import sqlite3
import sys
import json
import os
import atexit
import functools
from datetime import datetime, timezone
from typing import NoReturn, Optional
import hashlib

# LOCAL-SOC-SLM Blueprint v11.6.0 - Wazuh Proposal Adapter
# Appendix Q.3: Writeback Isolation Layer

DB_PATH: str = os.environ.get("WAZUH_PROPOSALS_DB", "/var/lib/wazuh-slm/proposals.db")

_db_initialized: bool = False
_db_connection: Optional[sqlite3.Connection] = None


class ProposalError(Exception):
    """Base exception for proposal adapter errors."""
    exit_code: int = 1
    default_message: str = "Proposal error"

    def __init__(self, message: Optional[str] = None, exit_code: Optional[int] = None):
        msg = message if message is not None else self.default_message
        super().__init__(msg)
        self.exit_code = exit_code if exit_code is not None else self.exit_code


class ProposalRejectedError(ProposalError):
    """Raised when a proposal is rejected (denylist, validation)."""
    exit_code = 1
    default_message = "Proposal rejected"


class ProposalStorageError(ProposalError):
    """Raised when database/storage operations fail."""
    exit_code = 2
    default_message = "Storage operation failed"


class ProposalDirectoryError(ProposalError):
    """Raised when required directory is missing."""
    exit_code = 3
    default_message = "Required directory missing"


class ProposalApprovalError(ProposalError):
    """Raised when approval validation fails."""
    exit_code = 4
    default_message = "Approval validation failed"


class ProposalSuccess(ProposalError):
    """Raised on successful proposal submission."""
    exit_code = 0
    default_message = "Proposal stored successfully"


def _get_connection() -> sqlite3.Connection:
    """Get or create a persistent database connection with WAL mode enabled."""
    global _db_connection
    if _db_connection is None:
        _db_connection = sqlite3.connect(DB_PATH)
        _db_connection.execute("PRAGMA journal_mode=WAL")
        _db_connection.execute("PRAGMA synchronous=NORMAL")
        _db_connection.execute("PRAGMA busy_timeout=5000")
        atexit.register(_close_connection)
    return _db_connection


def _close_connection() -> None:
    """Close the persistent database connection."""
    global _db_connection
    if _db_connection is not None:
        _db_connection.close()
        _db_connection = None


def init_db() -> None:
    """Initializes the SQLite database and creates the proposals table if it does not exist.

    Raises:
        ProposalStorageError: If database initialization fails.
    """
    global _db_initialized
    if _db_initialized:
        return
    try:
        conn = _get_connection()
        cursor = conn.cursor()
        cursor.execute('''CREATE TABLE IF NOT EXISTS proposals 
                          (id INTEGER PRIMARY KEY, key TEXT, value TEXT, 
                           status TEXT, created_at TIMESTAMP, changed_by TEXT)''')
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
        
        # Approval tokens table for approval-gated mutations (Section 24 compliance)
        cursor.execute('''CREATE TABLE IF NOT EXISTS approval_tokens
                          (id INTEGER PRIMARY KEY, token_hash TEXT UNIQUE,
                           description TEXT, created_at TIMESTAMP,
                           expires_at TIMESTAMP, is_active INTEGER DEFAULT 1)''')
        cursor.execute('''CREATE INDEX IF NOT EXISTS idx_approval_tokens_hash
                          ON approval_tokens(token_hash)''')
        
        # Trigger on INSERT to proposals
        cursor.execute('''CREATE TRIGGER IF NOT EXISTS audit_proposals_insert
                          AFTER INSERT ON proposals
                          BEGIN
                              INSERT INTO audit_log (proposal_id, action, old_status, new_status, changed_by, changed_at)
                              VALUES (NEW.id, 'INSERT', NULL, NEW.status, NEW.changed_by, datetime('now'));
                          END;''')
        
        # Trigger on UPDATE of status column in proposals
        cursor.execute('''CREATE TRIGGER IF NOT EXISTS audit_proposals_status_change
                          AFTER UPDATE OF status ON proposals
                          WHEN OLD.status != NEW.status
                          BEGIN
                              INSERT INTO audit_log (proposal_id, action, old_status, new_status, changed_by, changed_at)
                              VALUES (NEW.id, 'STATUS_CHANGE', OLD.status, NEW.status, NEW.changed_by, datetime('now'));
                          END;''')
        
        conn.commit()
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


@functools.lru_cache(maxsize=128)
def validate_approval_token(token: str) -> bool:
    """Validates an approval token against the approval_tokens table.

    Args:
        token: The approval token to validate.

    Returns:
        True if token is valid and active, False otherwise.
    """
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    
    try:
        conn = _get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT 1 FROM approval_tokens WHERE token_hash = ? AND is_active = 1 AND (expires_at IS NULL OR expires_at > datetime('now'))",
            (token_hash,)
        )
        result = cursor.fetchone()
        return result is not None
    except sqlite3.Error:
        return False


def parse_args() -> argparse.Namespace:
    """Parses command line arguments.

    Returns:
        Parsed arguments namespace with key, value, and approval_token attributes.
    """
    parser = argparse.ArgumentParser(description="Wazuh CDB Proposal Adapter")
    parser.add_argument("--key", required=True, help="CDB Key")
    parser.add_argument("--value", required=True, help="CDB Value")
    parser.add_argument("--approval-token", required=False, help="Approval token for gated mutation (Section 24)")
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


def store_proposal(key: str, value: str, approval_token: str | None = None) -> None:
    """Stores the proposal in the database after approval validation.

    Args:
        key: The CDB key.
        value: The CDB value.
        approval_token: Optional approval token for gated mutation.

    Raises:
        ProposalApprovalError: If approval token is missing or invalid.
        ProposalStorageError: If database operations fail.
    """
    # Approval-gated mutation: require valid approval token (Section 24)
    if approval_token is None:
        raise ProposalApprovalError("Approval token required for proposal submission (Section 24: Approval-gated mutations)")
    
    if not validate_approval_token(approval_token):
        raise ProposalApprovalError("Invalid or expired approval token")
    
    # Use token hash as actor identity for audit trail
    token_hash = hashlib.sha256(approval_token.encode()).hexdigest()
    
    try:
        init_db()
        conn = _get_connection()
        cursor = conn.cursor()
        cursor.execute("INSERT INTO proposals (key, value, status, created_at, changed_by) VALUES (?, ?, ?, ?, ?)",
                       (key, value, 'PENDING', datetime.now(timezone.utc), token_hash))
        conn.commit()
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
    store_proposal(args.key, args.value, args.approval_token)
    raise ProposalSuccess("Proposal stored successfully")


if __name__ == "__main__":
    try:
        main()
    except ProposalError as e:
        raise RuntimeError(e.exit_code) from e