import argparse
import sqlite3
import sys
import json
import os
import atexit
import functools
import threading
import time
from datetime import datetime, timezone
from typing import NoReturn, Optional, List, Tuple
import hashlib

# LOCAL-SOC-SLM Blueprint v11.6.0 - Wazuh Proposal Adapter
# Appendix Q.3: Writeback Isolation Layer

DB_PATH: str = os.environ.get("WAZUH_PROPOSALS_DB", "/var/lib/wazuh-slm/proposals.db")

_db_initialized: bool = False
_db_connection: Optional[sqlite3.Connection] = None

# Batch audit logging for high-throughput scenarios
_audit_batch: List[Tuple] = []
_audit_batch_lock = threading.Lock()
_AUDIT_BATCH_SIZE = int(os.environ.get("WAZUH_AUDIT_BATCH_SIZE", "100"))
_AUDIT_FLUSH_INTERVAL = float(os.environ.get("WAZUH_AUDIT_FLUSH_INTERVAL", "5.0"))
_AUDIT_MAX_RETRIES = int(os.environ.get("WAZUH_AUDIT_MAX_RETRIES", "3"))
_audit_flush_timer: Optional[threading.Timer] = None
_batch_mode_enabled = os.environ.get("WAZUH_AUDIT_BATCH_MODE", "false").lower() == "true"

# Dead-letter queue for entries that exceed max retries
_dead_letter_queue: List[Tuple] = []
_dead_letter_lock = threading.Lock()


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
    global _db_connection, _audit_flush_timer
    if _audit_flush_timer is not None:
        _audit_flush_timer.cancel()
        _audit_flush_timer = None
    _flush_audit_batch()
    if _db_connection is not None:
        _db_connection.close()
        _db_connection = None


def _flush_audit_batch() -> None:
    """Flush accumulated audit log entries to database."""
    global _audit_batch, _audit_flush_timer, _dead_letter_queue
    with _audit_batch_lock:
        if not _audit_batch:
            return
        batch = _audit_batch[:]
        _audit_batch.clear()
    
    if not batch:
        return
    
    try:
        conn = _get_connection()
        cursor = conn.cursor()
        cursor.executemany(
            "INSERT INTO audit_log (proposal_id, action, old_status, new_status, changed_by, changed_at) VALUES (?, ?, ?, ?, ?, ?)",
            batch
        )
        conn.commit()
    except sqlite3.Error:
        # On failure, increment retry count and re-queue entries that haven't exceeded max retries
        # Move entries that exceeded max retries to dead-letter queue
        retry_batch = []
        dead_letter_entries = []
        for entry in batch:
            # entry format: (proposal_id, action, old_status, new_status, changed_by, changed_at, retry_count)
            retry_count = entry[6] if len(entry) > 6 else 0
            if retry_count < _AUDIT_MAX_RETRIES:
                # Re-queue with incremented retry count
                retry_entry = entry[:6] + (retry_count + 1,)
                retry_batch.append(retry_entry)
            else:
                dead_letter_entries.append(entry)
        
        with _audit_batch_lock:
            # Prepend retry batch so they're tried first, but with backoff via timer
            _audit_batch = retry_batch + _audit_batch
        
        if dead_letter_entries:
            with _dead_letter_lock:
                _dead_letter_queue.extend(dead_letter_entries)
            # Log dead-letter entries to stderr for visibility
            for entry in dead_letter_entries:
                print(f"DEAD-LETTER: Audit entry failed after {_AUDIT_MAX_RETRIES} retries: {entry}", file=sys.stderr)
    finally:
        if _batch_mode_enabled:
            _schedule_audit_flush()


def _schedule_audit_flush() -> None:
    """Schedule the next audit batch flush."""
    global _audit_flush_timer
    if _audit_flush_timer is not None:
        _audit_flush_timer.cancel()
    _audit_flush_timer = threading.Timer(_AUDIT_FLUSH_INTERVAL, _flush_audit_batch)
    _audit_flush_timer.daemon = True
    _audit_flush_timer.start()


def _queue_audit_entry(proposal_id: int, action: str, old_status: Optional[str], 
                       new_status: str, changed_by: str) -> None:
    """Queue an audit entry for batch writing."""
    if not _batch_mode_enabled:
        return
    # Entry format: (proposal_id, action, old_status, new_status, changed_by, changed_at, retry_count)
    entry = (proposal_id, action, old_status, new_status, changed_by, datetime.now(timezone.utc), 0)
    with _audit_batch_lock:
        _audit_batch.append(entry)
        if len(_audit_batch) >= _AUDIT_BATCH_SIZE:
            _flush_audit_batch()
        else:
            _schedule_audit_flush()


def init_db() -> None:
    """Initializes the SQLite database and creates the proposals table if it does not exist.

    Raises:
        ProposalStorageError: If database initialization fails.
    """
    global _db_initialized, _audit_flush_timer
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
        
        # Trigger on INSERT to proposals (kept for compliance)
        # SQLite provides NEW.* for all columns in AFTER INSERT triggers.
        # Ensure changed_by is captured from the INSERT statement; default to 'system' if NULL.
        cursor.execute('''CREATE TRIGGER IF NOT EXISTS audit_proposals_insert
                          AFTER INSERT ON proposals
                          BEGIN
                              INSERT INTO audit_log (proposal_id, action, old_status, new_status, changed_by, changed_at)
                              VALUES (NEW.id, 'INSERT', NULL, NEW.status, COALESCE(NEW.changed_by, 'system'), datetime('now', 'utc'));
                          END;''')
        
        # Trigger on UPDATE of status column in proposals (kept for compliance)
        cursor.execute('''CREATE TRIGGER IF NOT EXISTS audit_proposals_status_change
                          AFTER UPDATE OF status ON proposals
                          WHEN OLD.status != NEW.status
                          BEGIN
                              INSERT INTO audit_log (proposal_id, action, old_status, new_status, changed_by, changed_at)
                              VALUES (NEW.id, 'STATUS_CHANGE', OLD.status, NEW.status, COALESCE(NEW.changed_by, 'system'), datetime('now', 'utc'));
                          END;''')
        
        conn.commit()
        _db_initialized = True
        
        if _batch_mode_enabled:
            _schedule_audit_flush()
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
    parser.add_argument("--changed-by", required=False, default="cli-user", help="Identity of the proposer")
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
        raise ProposalRejectedError(f"Key '{key}' is blocked by denylist (wazuh-internal- prefix)")


def submit_proposal(key: str, value: str, changed_by: str, approval_token: Optional[str] = None) -> int:
    """Submit a new proposal to the database.

    Args:
        key: The CDB key.
        value: The CDB value.
        changed_by: Identity of the proposer.
        approval_token: Optional approval token for gated mutations.

    Returns:
        The proposal ID.

    Raises:
        ProposalRejectedError: If key is blocked or approval token invalid.
        ProposalStorageError: If database operation fails.
    """
    validate_proposal(key)
    
    # If approval token provided, validate it
    if approval_token:
        if not validate_approval_token(approval_token):
            raise ProposalApprovalError("Invalid or expired approval token")
    
    try:
        conn = _get_connection()
        cursor = conn.cursor()
        now = datetime.now(timezone.utc)
        cursor.execute(
            "INSERT INTO proposals (key, value, status, created_at, changed_by) VALUES (?, ?, ?, ?, ?)",
            (key, value, "pending", now, changed_by)
        )
        proposal_id = cursor.lastrowid
        conn.commit()
        
        # Queue audit entry for batch processing (trigger also fires for compliance)
        _queue_audit_entry(proposal_id, "INSERT", None, "pending", changed_by)
        
        return proposal_id
    except sqlite3.Error as e:
        raise ProposalStorageError(f"Failed to submit proposal: {e}")


def main() -> NoReturn:
    """Main entry point for CLI."""
    args = parse_args()
    
    try:
        init_db()
        proposal_id = submit_proposal(args.key, args.value, args.changed_by, args.approval_token)
        print(f"Proposal stored with ID: {proposal_id}")
        sys.exit(0)
    except ProposalSuccess:
        sys.exit(0)
    except ProposalError as e:
        print(str(e), file=sys.stderr)
        sys.exit(2)
    except Exception as e:
        print(f"Unexpected error: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()